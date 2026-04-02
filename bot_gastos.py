import gspread
import os
import json
import re
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CommandHandler, ContextTypes
from datetime import datetime

# ── Configuración ──────────────────────────────────────────
TOKEN              = "8728321922:AAH19ysCMCgXKTzSrCV4A9R3ApQMZI2O5sc"
CHAT_ID            = "1008711489"
SHEET_ID           = "1ewM2suj2crbwrZkinizmEvZx3pVDuaR3yNG8VudvM6w"
CREDS              = "credenciales.json"
TASA_4X1000        = 0.004
# ───────────────────────────────────────────────────────────

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
}

PALABRAS_RESUMEN = ["dame el resumen", "quiero el resumen", "resumen del mes", "dame un resumen", "reporte"]
PALABRAS_SALDO   = ["dame el saldo", "dame mi saldo", "cuanto me queda", "cuánto me queda", "mi saldo", "ver saldo"]
PALABRAS_BORRAR  = ["borrar memoria", "borrar todo", "empezar de ceros", "resetear"]

def calcular_4x1000(total_gastos):
    return round(total_gastos * TASA_4X1000)

def conectar_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_json:
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1

def detectar_categoria(descripcion):
    descripcion = descripcion.lower()
    categorias = {
        "🍽️ Comida":          ["almuerzo", "comida", "restaurante", "pizza", "hamburguesa", "cafe", "desayuno", "cena", "empanada", "arepa"],
        "🛒 Mercado":         ["mercado", "supermercado", "exito", "jumbo", "d1", "ara", "verduras", "carnes"],
        "🚌 Transporte":      ["uber", "taxi", "bus", "transporte", "metro", "mio", "transmilenio", "gasolina"],
        "💳 Deudas":          ["cuota", "deuda", "credito", "prestamo", "banco", "tarjeta", "obligacion", "hipo", "abono"],
        "🎬 Entretenimiento": ["netflix", "spotify", "cine", "juego", "entretenimiento", "prime", "disney"],
        "💊 Salud":           ["farmacia", "medico", "salud", "drogas", "clinica", "medicina", "hospital"],
        "👕 Ropa":            ["ropa", "zapatos", "camisa", "pantalon", "vestido", "calzado"],
        "📱 Tecnología":      ["celular", "internet", "tecnologia", "computador", "cable", "plan"],
        "🏠 Hogar":           ["arriendo", "servicios", "agua", "luz", "gas", "hogar", "casa"],
        "🏧 Retiro":          ["retiro", "cajero", "efectivo"],
    }
    for categoria, palabras in categorias.items():
        if any(p in descripcion for p in palabras):
            return categoria
    return "📦 Otros"

def detectar_quincena_ingreso(descripcion):
    descripcion = descripcion.lower()
    if any(p in descripcion for p in ["primera", "q1", "quincena 1"]):
        return "Q1"
    elif any(p in descripcion for p in ["segunda", "q2", "quincena 2"]):
        return "Q2"
    return "Q2"

def obtener_quincena_activa(sheet):
    registros = sheet.get_all_records()
    for r in reversed(registros):
        if r["Categoría"] == "💵 Ingreso":
            return r["Quincena"]
    return "Q2"

def calcular_saldo_historico(sheet):
    registros = sheet.get_all_records()
    total_ingresos = 0
    total_gastos   = 0
    for r in registros:
        try:
            valor = float(r["Valor"])
            if r["Categoría"] == "💵 Ingreso":
                total_ingresos += valor
            else:
                total_gastos += valor
        except:
            continue
    return total_ingresos, total_gastos

def filtrar_registros_por_mes(registros, mes, anio):
    resultado = []
    for r in registros:
        try:
            fecha = datetime.strptime(r["Fecha"], "%d/%m/%Y")
            if fecha.month == mes and fecha.year == anio:
                resultado.append(r)
        except:
            continue
    return resultado

def filtrar_registros_por_rango(registros, fecha_inicio, fecha_fin):
    resultado = []
    for r in registros:
        try:
            fecha = datetime.strptime(r["Fecha"], "%d/%m/%Y")
            if fecha_inicio <= fecha <= fecha_fin:
                resultado.append(r)
        except:
            continue
    return resultado

def filtrar_registros_por_quincena(registros, quincena):
    return [r for r in registros if r.get("Quincena") == quincena]

def generar_resumen_registros(registros, titulo):
    total_ingresos = 0
    total_gastos   = 0
    categorias     = {}

    for r in registros:
        try:
            valor = float(r["Valor"])
            if r["Categoría"] == "💵 Ingreso":
                total_ingresos += valor
            else:
                total_gastos += valor
                cat = r["Categoría"] or "📦 Otros"
                categorias[cat] = categorias.get(cat, 0) + valor
        except:
            continue

    if not categorias and total_ingresos == 0:
        return f"📭 No hay registros en {titulo}."

    categorias_ord = sorted(categorias.items(), key=lambda x: x[1], reverse=True)
    detalle = ""
    for cat, val in categorias_ord:
        pct = (val / total_gastos * 100) if total_gastos > 0 else 0
        detalle += f"{cat}: ${val:,.0f} ({pct:.0f}%)\n"

    impuesto      = calcular_4x1000(total_gastos)
    disponible    = total_ingresos - total_gastos
    disponible_c4 = total_ingresos - total_gastos - impuesto

    return (
        f"📊 <b>Resumen — {titulo}</b>\n\n"
        f"{detalle}\n"
        f"💵 Total ingresos: ${total_ingresos:,.0f}\n"
        f"💸 Total gastado: ${total_gastos:,.0f}\n"
        f"🏦 4x1000 acumulado: ${impuesto:,.0f}\n\n"
        f"📊 Sin 4x1000: <b>${disponible:,.0f}</b>\n"
        f"📊 Con 4x1000: <b>${disponible_c4:,.0f}</b>"
    )

async def mostrar_saldo(update, sheet):
    total_ingresos, total_gastos = calcular_saldo_historico(sheet)
    impuesto      = calcular_4x1000(total_gastos)
    disponible    = total_ingresos - total_gastos
    disponible_c4 = total_ingresos - total_gastos - impuesto
    porcentaje    = (total_gastos / total_ingresos * 100) if total_ingresos > 0 else 0
    quincena      = obtener_quincena_activa(sheet)

    aviso = ""
    if total_ingresos == 0:
        aviso = "\n⚠️ <i>Aún no has registrado ningún ingreso.\nEscribe: ingreso: registro valor inicial 500000</i>"

    await update.message.reply_text(
        f"💰 <b>Tu saldo disponible</b>\n"
        f"📌 Quincena activa: <b>{quincena}</b>\n\n"
        f"Total ingresos: ${total_ingresos:,.0f}\n"
        f"Total gastado: ${total_gastos:,.0f} ({porcentaje:.0f}%)\n"
        f"🏦 4x1000 acumulado: ${impuesto:,.0f}\n\n"
        f"📊 Sin 4x1000: <b>${disponible:,.0f}</b>\n"
        f"📊 Con 4x1000: <b>${disponible_c4:,.0f}</b>"
        f"{aviso}",
        parse_mode="HTML"
    )

async def procesar_resumen(update, texto, sheet):
    registros = sheet.get_all_records()

    # Detectar rango: "de enero a marzo 2026"
    rango = re.search(r"de (\w+) a (\w+)(?: (\d{4}))?", texto)
    if rango:
        mes_inicio_str = rango.group(1)
        mes_fin_str    = rango.group(2)
        anio           = int(rango.group(3)) if rango.group(3) else datetime.now().year
        mes_inicio     = MESES.get(mes_inicio_str)
        mes_fin        = MESES.get(mes_fin_str)
        if mes_inicio and mes_fin:
            fecha_inicio = datetime(anio, mes_inicio, 1)
            ultimo_dia   = 31 if mes_fin in [1,3,5,7,8,10,12] else 30
            fecha_fin    = datetime(anio, mes_fin, ultimo_dia)
            filtrados    = filtrar_registros_por_rango(registros, fecha_inicio, fecha_fin)
            titulo       = f"{mes_inicio_str.capitalize()} a {mes_fin_str.capitalize()} {anio}"
            await update.message.reply_text(generar_resumen_registros(filtrados, titulo), parse_mode="HTML")
            return

    # Detectar mes específico: "de marzo 2026"
    mes_especifico = re.search(r"de (\w+)(?: (\d{4}))?", texto)
    if mes_especifico:
        mes_str = mes_especifico.group(1)
        anio    = int(mes_especifico.group(2)) if mes_especifico.group(2) else datetime.now().year
        mes     = MESES.get(mes_str)
        if mes:
            filtrados = filtrar_registros_por_mes(registros, mes, anio)
            titulo    = f"{mes_str.capitalize()} {anio}"
            await update.message.reply_text(generar_resumen_registros(filtrados, titulo), parse_mode="HTML")
            return

    # Detectar quincena
    if "q1" in texto:
        filtrados = filtrar_registros_por_quincena(registros, "Q1")
        await update.message.reply_text(generar_resumen_registros(filtrados, "Quincena 1"), parse_mode="HTML")
        return
    if "q2" in texto:
        filtrados = filtrar_registros_por_quincena(registros, "Q2")
        await update.message.reply_text(generar_resumen_registros(filtrados, "Quincena 2"), parse_mode="HTML")
        return

    # Resumen histórico completo
    await update.message.reply_text(generar_resumen_registros(registros, "Historial completo"), parse_mode="HTML")

async def borrar_memoria(update, sheet):
    sheet.clear()
    sheet.append_row(["Fecha", "Categoría", "Descripción", "Valor", "Quincena"])
    await update.message.reply_text(
        "🗑️ <b>Memoria borrada</b>\n"
        "Todo el historial fue eliminado. Empezamos de ceros. ✅",
        parse_mode="HTML"
    )

async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.chat_id) != CHAT_ID:
        return

    texto       = update.message.text.strip()
    texto_lower = texto.lower()
    sheet       = conectar_sheet()

    # Borrar memoria
    if any(p in texto_lower for p in PALABRAS_BORRAR):
        await borrar_memoria(update, sheet)
        return

    # Resumen
    if any(p in texto_lower for p in PALABRAS_RESUMEN):
        await procesar_resumen(update, texto_lower, sheet)
        return

    # Saldo
    if any(p in texto_lower for p in PALABRAS_SALDO):
        await mostrar_saldo(update, sheet)
        return

    # Ingreso
    if texto_lower.startswith("ingreso:"):
        contenido = texto[8:].strip()
        partes    = contenido.rsplit(" ", 1)
        if len(partes) != 2:
            await update.message.reply_text(
                "⚠️ Formato incorrecto. Ejemplo:\n"
                "<i>ingreso: pago segunda quincena 2200000</i>",
                parse_mode="HTML"
            )
            return
        descripcion = partes[0].strip()
        try:
            valor = float(partes[1].replace(",", "").replace(".", ""))
        except:
            await update.message.reply_text("⚠️ El valor debe ser un número.", parse_mode="HTML")
            return

        fecha    = datetime.now()
        quincena = detectar_quincena_ingreso(descripcion)
        sheet.append_row([fecha.strftime("%d/%m/%Y"), "💵 Ingreso", descripcion, valor, quincena])
        total_ingresos, total_gastos = calcular_saldo_historico(sheet)
        impuesto      = calcular_4x1000(total_gastos)
        disponible    = total_ingresos - total_gastos
        disponible_c4 = total_ingresos - total_gastos - impuesto

        await update.message.reply_text(
            f"✅ <b>Ingreso registrado</b>\n"
            f"📌 Quincena: <b>{quincena}</b>\n"
            f"💵 {descripcion}: ${valor:,.0f}\n\n"
            f"Total ingresos: ${total_ingresos:,.0f}\n"
            f"Total gastado: ${total_gastos:,.0f}\n"
            f"🏦 4x1000 acumulado: ${impuesto:,.0f}\n\n"
            f"📊 Sin 4x1000: <b>${disponible:,.0f}</b>\n"
            f"📊 Con 4x1000: <b>${disponible_c4:,.0f}</b>",
            parse_mode="HTML"
        )
        return

    # Egreso
    if texto_lower.startswith("egreso:"):
        contenido = texto[7:].strip()
        partes    = contenido.rsplit(" ", 1)
        if len(partes) != 2:
            await update.message.reply_text(
                "⚠️ Formato incorrecto. Ejemplo:\n"
                "<i>egreso: almuerzo 15000</i>",
                parse_mode="HTML"
            )
            return
        descripcion = partes[0].strip()
        try:
            valor = float(partes[1].replace(",", "").replace(".", ""))
        except:
            await update.message.reply_text("⚠️ El valor debe ser un número.", parse_mode="HTML")
            return

        fecha         = datetime.now()
        quincena      = obtener_quincena_activa(sheet)
        categoria     = detectar_categoria(descripcion)
        sheet.append_row([fecha.strftime("%d/%m/%Y"), categoria, descripcion, valor, quincena])
        total_ingresos, total_gastos = calcular_saldo_historico(sheet)
        impuesto      = calcular_4x1000(total_gastos)
        disponible    = total_ingresos - total_gastos
        disponible_c4 = total_ingresos - total_gastos - impuesto

        await update.message.reply_text(
            f"✅ <b>Egreso registrado</b>\n"
            f"📌 Quincena: <b>{quincena}</b>\n"
            f"{categoria} {descripcion}\n"
            f"💵 ${valor:,.0f}\n\n"
            f"Total gastado: ${total_gastos:,.0f}\n"
            f"🏦 4x1000 acumulado: ${impuesto:,.0f}\n\n"
            f"📊 Sin 4x1000: <b>${disponible:,.0f}</b>\n"
            f"📊 Con 4x1000: <b>${disponible_c4:,.0f}</b>",
            parse_mode="HTML"
        )
        return

    # No entendió
    await update.message.reply_text(
        "⚠️ No entendí. Ejemplos:\n\n"
        "<i>ingreso: pago segunda quincena 2200000</i>\n"
        "<i>ingreso: pago primera quincena 2800000</i>\n"
        "<i>egreso: almuerzo 15000</i>\n"
        "<i>egreso: pago credito hipo 340000</i>\n"
        "<i>dame el saldo</i>\n"
        "<i>dame el resumen</i>\n"
        "<i>dame el resumen de marzo 2026</i>\n"
        "<i>dame el resumen de enero a marzo 2026</i>\n"
        "<i>dame el resumen de q1</i>\n"
        "<i>borrar memoria</i>",
        parse_mode="HTML"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>Hola Alexis!</b>\n\n"
        "<b>¿Cómo registrar?</b>\n\n"
        "💵 <b>Ingresos:</b>\n"
        "<i>ingreso: pago primera quincena 2800000</i>\n"
        "<i>ingreso: pago segunda quincena 2200000</i>\n"
        "<i>ingreso: registro valor inicial 1732483</i>\n\n"
        "💸 <b>Egresos:</b>\n"
        "<i>egreso: almuerzo 15000</i>\n"
        "<i>egreso: pago credito hipo 340000</i>\n"
        "<i>egreso: retiro cajero 50000</i>\n\n"
        "💰 <b>Ver saldo:</b>\n"
        "<i>dame el saldo</i>\n\n"
        "📊 <b>Ver resumen:</b>\n"
        "<i>dame el resumen</i>\n"
        "<i>dame el resumen de marzo 2026</i>\n"
        "<i>dame el resumen de enero a marzo 2026</i>\n"
        "<i>dame el resumen de q1</i>\n\n"
        "🗑️ <b>Borrar historial:</b>\n"
        "<i>borrar memoria</i>",
        parse_mode="HTML"
    )

app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))

print("🤖 Bot de gastos iniciado...")
app.run_polling()
