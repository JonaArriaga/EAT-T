from flask import Flask, request, render_template_string
import datetime
import requests
import boto3
import uuid

app = Flask(__name__)

# --------------------------------------------
# 🔵 CONFIGURACIÓN DynamoDB LOCAL
# --------------------------------------------
dynamodb = boto3.resource(
    'dynamodb',
    region_name='sa-east-1',
    endpoint_url='http://localhost:8000'
)

TABLA = dynamodb.Table("Alimentos")

# --------------------------------------------
# 🔵 HTML (igual que el tuyo)
# --------------------------------------------
HTML_FORM = """ 
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Escáner de Alimentos</title>
<script src="https://unpkg.com/html5-qrcode" type="text/javascript"></script>
<style>
body { font-family: Arial; background-color: #f8f9fa; text-align: center; margin-top: 30px; }
#reader { width: 300px; margin: 0 auto; }
input, button { font-size: 18px; padding: 10px; margin: 10px; width: 80%; max-width: 320px; }
button { background-color: #28a745; color: white; border: none; border-radius: 8px; cursor:pointer; }
a { display: block; margin-top: 20px; color: #007bff; text-decoration: none; font-size: 18px; }
#upload-section { margin-top: 20px; }
#file-input { display: none; }
label.upload-label {
  display: inline-block; background-color: #17a2b8; color: white;
  padding: 10px 20px; border-radius: 8px; cursor: pointer;
}
</style>
</head>
<body>
<h2>📱 Escanear alimento con cámara o subir imagen</h2>
<div id="reader"></div>

<form id="form" action="/agregar" method="POST">
  <input type="number" name="cantidad" placeholder="Cantidad" min="1" required><br>
  <input type="text" name="fecha_venc" placeholder="Fecha de vencimiento (DD/MM/AAAA)" pattern="\\d{2}/\\d{2}/\\d{4}"><br>
  <input type="hidden" id="codigo" name="codigo" required>
  <button type="submit">Enviar</button>
</form>

<div id="upload-section">
  <label for="file-input" class="upload-label">📸 Subir imagen desde galería</label>
  <input type="file" id="file-input" accept="image/*">
</div>

<a href="/inventario">📦 Ver inventario actual</a>

<script src="https://unpkg.com/quagga@0.12.1/dist/quagga.min.js"></script>

<script>
// ---- LECTURA DE CÓDIGO DESDE IMAGEN ----
document.getElementById("file-input").addEventListener("change", function(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function() {
        const imageDataUrl = reader.result;

        let tempDiv = document.createElement("div");
        tempDiv.id = "temp-quagga";
        tempDiv.style.display = "none";
        document.body.appendChild(tempDiv);

        Quagga.decodeSingle({
            src: imageDataUrl,
            inputStream: { size: 800, target: document.querySelector('#temp-quagga') },
            numOfWorkers: 0,
            decoder: { readers: ["ean_reader","ean_8_reader","upc_reader","upc_e_reader","code_128_reader"] }
        }, function(result) {
            document.body.removeChild(tempDiv);
            if (result && result.codeResult) {
                const code = result.codeResult.code;
                document.getElementById("codigo").value = code;
                alert("✅ Código detectado: " + code + "\\nAhora completa los demás campos antes de enviar.");
            } else {
                alert("❌ No se pudo leer el código de barras. Intenta otra imagen con más luz.");
            }
        });
    };
    reader.readAsDataURL(file);
});
</script>

</body>
</html>
"""

# --------------------------------------------
# 🔵 Fun: Guardar en DynamoDB
# --------------------------------------------
def agregar_alimento(codigo, cantidad=1, fecha_venc="N/A"):
    try:
        resp = requests.get(f"https://world.openfoodfacts.org/api/v2/product/{codigo}.json", timeout=5)
        data = resp.json()

        if data.get("status") == 1:
            prod = data["product"]
            tipo = prod.get("product_name", "Desconocido")
            marca = prod.get("brands", "N/A")
            info_extra = f"Marca: {marca}"
        else:
            tipo = "Producto no encontrado"
            info_extra = ""
    except Exception as e:
        tipo = "Error de conexión"
        info_extra = str(e)

    fecha_compra = datetime.date.today().strftime("%d/%m/%Y")
    ts = datetime.datetime.utcnow().isoformat()

    TABLA.put_item(
        Item={
            "codigo": str(codigo),
            "ts": ts,
            "tipo": tipo,
            "cantidad": int(cantidad),
            "fecha_compra": fecha_compra,
            "fecha_venc": fecha_venc or "N/A",
            "info": info_extra,
        }
    )
    
# --------------------------------------------
# 🔵 Rutas
# --------------------------------------------
@app.route("/")
def index():
    return render_template_string(HTML_FORM)

@app.route("/agregar", methods=["POST"])
def recibir_codigo():
    codigo = request.form.get("codigo")
    cantidad = request.form.get("cantidad", "1")
    fecha_venc = request.form.get("fecha_venc", "N/A")

    agregar_alimento(codigo, cantidad, fecha_venc)

    return f"""
    <h3>✅ Producto agregado</h3>
    <p><b>Código:</b> {codigo}</p>
    <p><b>Cantidad:</b> {cantidad}</p>
    <p><b>Fecha de vencimiento:</b> {fecha_venc}</p>
    <a href="/">⬅ Volver</a>
    <br><a href="/inventario">📦 Ver inventario</a>
    """

@app.route("/inventario")
def inventario():
    # Escanea la tabla completa
    datos = TABLA.scan().get("Items", [])

    html = """
    <h2>📦 Inventario</h2>
    <table border='1' cellpadding='8'>
    <tr>
      <th>Código</th><th>Tipo</th><th>Cantidad</th>
      <th>Fecha Compra</th><th>Fecha Venc</th><th>Info</th>
    </tr>
    """

    for item in sorted(datos, key=lambda x: (x["codigo"], x["ts"])):
        html += f"""
        <tr>
          <td>{item['codigo']}</td>
          <td>{item['tipo']}</td>
          <td>{item['cantidad']}</td>
          <td>{item['fecha_compra']}</td>
          <td>{item['fecha_venc']}</td>
          <td>{item['info']}</td>
        </tr>
        """

    html += "</table><br><a href='/'>⬅ Volver</a>"
    return html


# --------------------------------------------
# 🔵 Iniciar servidor
# --------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

