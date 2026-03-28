import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CommandHandler, ContextTypes
from datetime import datetime
import calendar
import os
import json

# ── Configuración ──────────────────────────────────────────
TOKEN              = "8728321922:AAH19ysCMCgXKTzSrCV4A9R3ApQMZI2O5sc"
CHAT_ID            = "1008711489"
SHEET_ID           = "1ewM2suj2crbwrZkinizmEvZx3pVDuaR3yNG8VudvM6w"
CREDS              = "credenciales.json"
PRESUPUESTO_Q1     = 2800000
PRESUPUESTO_Q2     = 2200000
ALERTA_PORCENTAJE  = 0.70
CRITICO_PORCENTAJE = 0.90
# ───────────────────────────────────────────────────────────

PALABRAS_INGRESO = ["pago", "ingreso", "quincena", "salario", "sueldo", "me pagaron", "cobré"]
PALABRAS_RESUMEN = ["resumen", "dame el resumen", "quiero el resumen", "resumen del mes"]
PALABRAS_SALDO   = ["saldo", "dame el saldo", "dame mi saldo", "cuanto me queda", "cuánto me queda", "mi saldo"]
PALABRAS_BORRAR  = ["borrar memoria", "borrar todo", "empezar de ceros", "resetear"]

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
        "💳 Deudas":          ["cuota", "deuda", "credito", "prestamo", "banco", "tarjeta", "obligacion"],
        "🎬 Entretenimiento": ["netflix", "spotify", "cine", "juego", "entretenimiento", "prime", "disney"],
        "💊 Salud":           ["farmacia", "medico", "salud", "drogas", "clinica", "medicina", "hospital"],
        "👕 Ropa":            ["ropa", "zapatos", "camisa", "pantalon", "vestido", "calzado"],
        "📱 Tecnología":      ["celular", "internet", "tecnologia", "computador", "cable", "plan"],
        "🏠 Hogar":           ["arriendo", "servicios", "agua", "luz", "gas", "hogar", "casa"],
    }
    for categoria, palabras in categorias.items():
        if any(p in descripcion for p in palabras):
            return categoria
    return "📦 Otros"

def obtener_quincena(fecha):
    return "Q1" if fecha.day <= 15 else "Q2"

def tiene_ingreso_quincena(sheet, quincena, mes, anio):
    registros = sheet.get_all_records()
    for r in registros:
        try:
            fecha = datetime.strptime(r["Fecha"], "%d/%m/%Y")
            if fecha.month == mes and fecha.year == anio and r["Quincena"] == quincena and r["Categoría"] == "💵 Ingreso":
                return True
        except:
            continue
    return False

def obtener_gastos_quincena(sheet, quincena, mes, anio):
    registros = sheet.get_all_records()
    total = 0
    for r in registros:
        try:
            fecha = datetime.strptime(r["Fecha"], "%d/%m/%Y")
            if fecha.month == mes and fecha.year == anio and r["Quincena"] == quincena:
                if r["Categoría"] != "💵 Ingreso":
                    total += float(r["Valor"])
        except:
            continue
    return total

async def verificar_alerta(update, quincena, total_gastado):
    presupuesto = PRESUPUESTO_Q1 if quincena == "Q1" else PRESUPUESTO_Q2
    porcentaje  = total_gastado / presupuesto

    if porcentaje >= CRITICO_PORCENTAJE:
        restante = presupuesto - total_gastado
        await update.message.reply_text(
            f"🚨 <b>ALERTA CRÍTICA</b>\n"
            f"Llevas gastado el <b>{porcentaje*100:.0f}%</b> de tu quincena\n"
            f"Gastado: ${total_gastado:,.0f}\n"
            f"Presupuesto: ${presupuesto:,.0f}\n"
            f"Te quedan: <b>${restante:,.0f}</b>\n"
            f"⚠️ Estás casi sin presupuesto",
            parse_mode="HTML"
        )
    elif porcentaje >= ALERTA_PORCENTAJE:
        restante = presupuesto - total_gastado
        await update.message.reply_text(
            f"⚠️ <b>ALERTA</b>\n"
            f"Llevas gastado el <b>{porcentaje*100:.0f}%</b> de tu quincena\n"
            f"Gastado: ${total_gastado:,.0f}\n"
            f"Presupuesto: ${presupuesto:,.0f}\n"
            f"Te quedan: <b>${restante:,.0f}</b>",
            parse_mode="HTML"
        )

async def mostrar_saldo(update):
    fecha       = datetime.now()
    quincena    = obtener_quincena(fecha)
    sheet       = conectar_sheet()
    total       = obtener_gastos_quincena(sheet, quincena, fecha.month, fecha.year)
    presupuesto = PRESUPUESTO_Q1 if quincena == "Q1" else PRESUPUESTO_Q2
    restante    = presupuesto - total
    porcentaje  = (total / presupuesto) * 100

    # Verificar si registró el ingreso
    aviso_ingreso = ""
    if not tiene_ingreso_quincena(sheet, quincena, fecha.month, fecha.year):
        aviso_ingreso = f"\n⚠️ <i>Aún no has registrado el ingreso de esta quincena.\nEscribe: pago quincena {presupuesto:,.0f}</i>"

    await update.message.reply_text(
        f"💰 <b>Saldo quincena {quincena}</b>\n\n"
        f"Presupuesto: ${presupuesto:,.0f}\n"
        f"Gastado: ${total:,.0f} ({porcentaje:.0f}%)\n"
        f"Disponible: <b>${restante:,.0f}</b>"
        f"{aviso_ingreso}",
        parse_mode="HTML"
    )

async def mostrar_resumen(update):
    fecha       = datetime.now()
    sheet       = conectar_sheet()
    registros   = sheet.get_all_records()
    mes_actual  = fecha.month
    anio_actual = fecha.year
    nombre_mes  = calendar.month_name[mes_actual]

    total      = 0
    categorias = {}

    for r in registros:
        try:
            f = datetime.strptime(r["Fecha"], "%d/%m/%Y")
            if f.month == mes_actual and f.year == anio_actual and r["Categoría"] != "💵 Ingreso":
                valor = float(r["Valor"])
                total += valor
                cat   = r["Categoría"] or "📦 Otros"
                categorias[cat] = categorias.get(cat, 0) + valor
        except:
            continue

    if not categorias:
        await update.message.reply_text(f"📭 No hay gastos registrados en {nombre_mes}.")
        return

    categorias_ord = sorted(categorias.items(), key=lambda x: x[1], reverse=True)
    detalle = ""
    for cat, val in categorias_ord:
        pct = (val / total) * 100
        detalle += f"{cat}: ${val:,.0f} ({pct:.0f}%)\n"

    await update.message.reply_text(
        f"📊 <b>Resumen de {nombre_mes} {anio_actual}</b>\n\n"
        f"{detalle}\n"
        f"💸 <b>Total gastado: ${total:,.0f}</b>\n"
        f"💵 Salario mensual: $5.000.000\n"
        f"📉 Disponible: ${5000000 - total:,.0f}",
        parse_mode="HTML"
    )

async def borrar_memoria(update):
    sheet = conectar_sheet()
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

    texto = update.message.text.strip().lower()

    # Detectar borrar memoria
    if any(p in texto for p in PALABRAS_BORRAR):
        await borrar_memoria(update)
        return

    # Detectar resumen
    if any(p in texto for p in PALABRAS_RESUMEN):
        await mostrar_resumen(update)
        return

    # Detectar saldo
    if any(p in texto for p in PALABRAS_SALDO):
        await mostrar_saldo(update)
        return

    # Registrar gasto o ingreso
    partes = update.message.text.strip().rsplit(" ", 1)
    if len(partes) != 2:
        await update.message.reply_text(
            "⚠️ No entendí. Ejemplos:\n"
            "<i>almuerzo 15000</i>\n"
            "<i>pago primera quincena 2800000</i>\n"
            "<i>dame el saldo</i>\n"
            "<i>dame el resumen</i>\n"
            "<i>borrar memoria</i>",
            parse_mode="HTML"
        )
        return

    descripcion = partes[0].strip()
    try:
        valor = float(partes[1].replace(",", "").replace(".", ""))
    except:
        await update.message.reply_text(
            "⚠️ No entendí. Ejemplos:\n"
            "<i>almuerzo 15000</i>\n"
            "<i>pago primera quincena 2800000</i>\n"
            "<i>dame el saldo</i>\n"
            "<i>dame el resumen</i>\n"
            "<i>borrar memoria</i>",
            parse_mode="HTML"
        )
        return

    fecha    = datetime.now()
    quincena = obtener_quincena(fecha)
    sheet    = conectar_sheet()

    if any(p in descripcion.lower() for p in PALABRAS_INGRESO):
        sheet.append_row([fecha.strftime("%d/%m/%Y"), "💵 Ingreso", descripcion, valor, quincena])
        await update.message.reply_text(
            f"✅ <b>Ingreso registrado</b>\n"
            f"💵 ${valor:,.0f} — Quincena {quincena}",
            parse_mode="HTML"
        )
    else:
        categoria     = detectar_categoria(descripcion)
        sheet.append_row([fecha.strftime("%d/%m/%Y"), categoria, descripcion, valor, quincena])
        presupuesto   = PRESUPUESTO_Q1 if quincena == "Q1" else PRESUPUESTO_Q2
        total_gastado = obtener_gastos_quincena(sheet, quincena, fecha.month, fecha.year)
        restante      = presupuesto - total_gastado

        await update.message.reply_text(
            f"✅ <b>Registrado</b>\n"
            f"{categoria} {descripcion}\n"
            f"💵 ${valor:,.0f}\n\n"
            f"📊 Quincena {quincena}: ${total_gastado:,.0f} / ${presupuesto:,.0f}\n"
            f"💰 Te quedan: <b>${restante:,.0f}</b>",
            parse_mode="HTML"
        )
        await verificar_alerta(update, quincena, total_gastado)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>Hola Alexis!</b>\n\n"
        "Escríbeme de forma natural:\n\n"
        "📝 <b>Registrar gasto:</b>\n"
        "<i>almuerzo 15000</i>\n\n"
        "💵 <b>Registrar ingreso:</b>\n"
        "<i>pago primera quincena 2800000</i>\n\n"
        "💰 <b>Ver saldo:</b>\n"
        "<i>dame el saldo</i>\n\n"
        "📊 <b>Ver resumen:</b>\n"
        "<i>dame el resumen</i>\n\n"
        "🗑️ <b>Borrar historial:</b>\n"
        "<i>borrar memoria</i>",
        parse_mode="HTML"
    )

app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))

print("🤖 Bot de gastos iniciado...")
app.run_polling()