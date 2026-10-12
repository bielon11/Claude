"""Genera los sub-workflows de los dos asistentes de WhatsApp: secretario interno y chatbot de clientes."""
import sys, pathlib
from common import *

BASE = pathlib.Path(__file__).resolve().parent.parent
OPENAI = "{ openAiApi: { id: 'sBeNn2zvBvjvV7Ci', name: 'OpenAI account' } }"
TEL = "$('Entrada').first().json.telefono"
CALENDARIO = ("Calendario del restaurante (Europe/Madrid). Ahora: {{ $now.setZone('Europe/Madrid').setLocale('es').toFormat(\"cccc d 'de' LLLL yyyy, HH:mm\") }}.\n"
              "Próximos días: {{ Array.from({ length: 8 }, (_, i) => { const d = $now.setZone('Europe/Madrid').plus({ days: i }); "
              "return (i === 0 ? 'hoy' : i === 1 ? 'mañana' : d.setLocale('es').toFormat('cccc')) + ' ' + d.setLocale('es').toFormat('d LLL') + ' = ' + d.toFormat('yyyy-MM-dd'); }).join(' · ') }}")


def fa(nombre, desc, tipo='string'):
    return "={{ $fromAI(" + J(nombre) + ", " + J(desc) + ", " + J(tipo) + ") }}"


F_FECHA = fa('fecha', 'Fecha YYYY-MM-DD según el calendario del mensaje (también vale "hoy" o "mañana")')
F_HORA = fa('hora', 'Hora de inicio HH:MM en 24 h')
F_PERS = fa('personas', 'Número total de comensales', 'number')
F_ZONA = fa('zona', 'Interior o Terraza. Vacío si da igual')


def herramienta(var, nombre, desc, valores, pos):
    return f"""const {var} = tool({{ type: '@n8n/n8n-nodes-langchain.toolWorkflow', version: 2.2, config: {{ name: {J(nombre)}, position: {pos},
  parameters: {{ description: {J(desc)}, source: 'database', workflowId: {motor_rl()}, workflowInputs: {llamar_motor(valores, True)} }} }} }});"""


def agente_wf(wid, titulo, agente_nombre, prompt_file, intro, herramientas, memoria_clave, fallback, nota_txt, error_wf):
    system = (BASE / prompt_file).read_text()
    texto = intro + "\n" + CALENDARIO + "\n\nMensaje ({{ $('Entrada').first().json.tipo_mensaje }}):\n{{ $('Entrada').first().json.texto }}"
    tools_code = '\n'.join(herramienta(*h) for h in herramientas)
    tool_vars = ', '.join(h[0] for h in herramientas)
    return f"""import {{ workflow, node, trigger, sticky, languageModel, memory, tool, expr }} from '@n8n/workflow-sdk';
const entrada = trigger({{ type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2, config: {{ name: 'Entrada', position: [0, 0], parameters: {{ inputSource: 'workflowInputs', workflowInputs: {{ values: [ {{ name: 'texto', type: 'string' }}, {{ name: 'telefono', type: 'string' }}, {{ name: 'nombre_perfil', type: 'string' }}, {{ name: 'tipo_mensaje', type: 'string' }} ] }} }} }}, output: [{{ texto: 'hola', telefono: '34600000000', nombre_perfil: 'x', tipo_mensaje: 'texto' }}] }});
const modelo = languageModel({{ type: '@n8n/n8n-nodes-langchain.lmChatOpenAi', version: 1.3, config: {{ name: 'Modelo OpenAI', position: [200, 260], credentials: {OPENAI}, parameters: {{ model: {{ __rl: true, mode: 'list', value: 'gpt-5.4-mini', cachedResultName: 'gpt-5.4-mini' }}, builtInTools: {{}}, options: {{}} }} }} }});
const memoria = memory({{ type: '@n8n/n8n-nodes-langchain.memoryBufferWindow', version: 1.4, config: {{ name: 'Memoria por conversación', position: [360, 260], parameters: {{ sessionIdType: 'customKey', sessionKey: {E(memoria_clave)}, contextWindowLength: 15 }} }} }});
{tools_code}
const agente = node({{ type: '@n8n/n8n-nodes-langchain.agent', version: 3.1, config: {{ name: {J(agente_nombre)}, position: [300, 0], onError: 'continueRegularOutput',
  parameters: {{ promptType: 'define', text: {E(texto)}, options: {{ systemMessage: {J(system)} }} }},
  subnodes: {{ model: modelo, memory: memoria, tools: [ {tool_vars} ] }} }}, output: [{{ output: 'texto' }}] }});
const respuesta = node({{ type: 'n8n-nodes-base.set', version: 3.4, config: {{ name: 'Respuesta', position: [700, 0], parameters: {set_fields([('respuesta', 'string', '={{ $json.output || ' + J(fallback) + ' }}')])} }}, output: [{{ respuesta: 'texto' }}] }});
const nota = sticky({J(nota_txt)}, [entrada, agente, respuesta], {{ color: 4 }});
export default workflow({J(wid)}, {J(titulo)}).add(entrada).to(agente).to(respuesta).add(nota);
"""


S = '={{ ' + TEL + ' }}'
secretario_tools = [
    ('tConsultar', 'Consultar reservas', 'Lista las reservas confirmadas de un día o rango (con totales de reservas y personas por zona y por comida/cena, y bloqueos de agenda). Úsala para cualquier pregunta sobre reservas, ocupación o cuánta gente viene.',
     {'accion': 'listar', 'origen': 'secretario', 'actor_telefono': S, 'fecha': F_FECHA,
      'fecha_hasta': fa('fecha_hasta', 'Último día del rango YYYY-MM-DD. Vacío si es un solo día'),
      'franja': fa('franja', 'comida, cena o vacío para todo el día'), 'zona': F_ZONA,
      'texto_busqueda': fa('incluir_canceladas', 'Escribe incluir_canceladas solo si piden ver también las canceladas; si no, vacío')}, '[0, 420]'),
    ('tBuscar', 'Buscar reserva', 'Busca reservas (de hoy en adelante, o desde una fecha) por nombre del cliente o por teléfono. Devuelve sus códigos.',
     {'accion': 'buscar', 'origen': 'secretario', 'actor_telefono': S, 'texto_busqueda': fa('texto_busqueda', 'Nombre (o parte) o teléfono del cliente'),
      'fecha': fa('fecha', 'Fecha YYYY-MM-DD desde la que buscar. Vacío = desde hoy')}, '[140, 420]'),
    ('tDisp', 'Consultar disponibilidad', 'Comprueba si hay sitio (y cuántas plazas libres por zona) para una fecha, hora y número de personas. No reserva nada.',
     {'accion': 'disponibilidad', 'origen': 'secretario', 'actor_telefono': S, 'fecha': F_FECHA, 'hora': F_HORA, 'personas': F_PERS, 'zona': F_ZONA}, '[280, 420]'),
    ('tCrear', 'Crear reserva', 'Crea una reserva. Necesita nombre, fecha, hora y personas. Úsala solo con todos los datos claros (o tras confirmar lo que hayas supuesto).',
     {'accion': 'crear', 'origen': 'secretario', 'actor_telefono': S, 'nombre': fa('nombre', 'Nombre de la reserva'),
      'telefono_cliente': fa('telefono_cliente', 'Teléfono del cliente con prefijo de país (34...). Vacío si no lo dan'),
      'fecha': F_FECHA, 'hora': F_HORA, 'personas': F_PERS, 'zona': F_ZONA,
      'observaciones': fa('observaciones', 'Alergias, trona, celebración u otras notas. Vacío si no hay')}, '[420, 420]'),
    ('tModificar', 'Modificar reserva', 'Cambia día, hora, personas, zona, nombre u observaciones de una reserva identificada por su código. Comprueba la disponibilidad; si no hay sitio la reserva no cambia.',
     {'accion': 'modificar', 'origen': 'secretario', 'actor_telefono': S, 'reserva_ref': fa('reserva_ref', 'Código de la reserva (R...)'),
      'fecha': fa('fecha', 'Nueva fecha YYYY-MM-DD o vacío para mantenerla'), 'hora': fa('hora', 'Nueva hora HH:MM o vacío para mantenerla'),
      'personas': fa('personas', 'Nuevo número de personas o 0 para mantenerlo', 'number'), 'zona': fa('zona', 'Nueva zona (Interior o Terraza) o vacío para mantenerla'),
      'nombre': fa('nombre', 'Nuevo nombre o vacío para mantenerlo'), 'observaciones': fa('observaciones', 'Nuevas observaciones o vacío para mantenerlas')}, '[560, 420]'),
    ('tCancelar', 'Cancelar reserva', 'Cancela una reserva por su código. Úsala solo tras confirmación explícita.',
     {'accion': 'cancelar', 'origen': 'secretario', 'actor_telefono': S, 'reserva_ref': fa('reserva_ref', 'Código de la reserva (R...)')}, '[700, 420]'),
    ('tBloquear', 'Bloquear agenda', 'Solo admin. Cierra una zona o retiene plazas en un día y franja horaria (evento, lluvia, cierre). Úsala solo tras confirmación explícita.',
     {'accion': 'bloquear', 'origen': 'secretario', 'actor_telefono': S, 'fecha': F_FECHA, 'hora': fa('hora', 'Desde (HH:MM). Vacío = todo el día'),
      'hora_hasta': fa('hora_hasta', 'Hasta (HH:MM). Vacío = fin del día'), 'zona': fa('zona', 'Interior, Terraza o Todas'),
      'plazas': fa('plazas', 'Plazas a retener. 0 = zona completa', 'number'), 'motivo': fa('motivo', 'Motivo del bloqueo')}, '[840, 420]'),
    ('tDesbloquear', 'Quitar bloqueo de agenda', 'Solo admin. Anula un bloqueo de agenda por su código (B...).',
     {'accion': 'desbloquear', 'origen': 'secretario', 'actor_telefono': S, 'reserva_ref': fa('reserva_ref', 'Código del bloqueo (B...)')}, '[980, 420]'),
    ('tVerBloqueos', 'Ver bloqueos de agenda', 'Lista los bloqueos de agenda activos desde una fecha (por defecto hoy) y los días de cierre fijos.',
     {'accion': 'listar_bloqueos', 'origen': 'secretario', 'actor_telefono': S, 'fecha': fa('fecha', 'Fecha YYYY-MM-DD desde la que listar. Vacío = hoy')}, '[1120, 420]'),
]

C = '={{ ' + TEL + ' }}'
cliente_tools = [
    ('tDisp', 'Consultar disponibilidad', 'Comprueba con los datos reales (horarios, cierres y plazas libres por zona) si hay sitio para una fecha, hora, número de personas y zona. Si no hay sitio devuelve alternativas ya verificadas. Úsala SIEMPRE antes de proponer una hora. No reserva nada.',
     {'accion': 'disponibilidad', 'origen': 'whatsapp', 'telefono_cliente': C, 'fecha': F_FECHA, 'hora': F_HORA, 'personas': F_PERS, 'zona': F_ZONA}, '[0, 420]'),
    ('tCrear', 'Crear reserva', 'Crea la reserva. Úsala SOLO cuando tengas nombre, fecha, hora y número de personas y el cliente haya confirmado explícitamente el resumen. Si responde ok=false, explica el motivo y ofrece las alternativas devueltas.',
     {'accion': 'crear', 'origen': 'whatsapp', 'telefono_cliente': C, 'nombre': fa('nombre', 'Nombre de la persona que reserva'), 'fecha': F_FECHA, 'hora': F_HORA, 'personas': F_PERS, 'zona': F_ZONA,
      'observaciones': fa('observaciones', 'Alergias, trona, celebración, accesibilidad u otras peticiones. Vacío si no hay')}, '[160, 420]'),
    ('tVer', 'Ver reservas del cliente', 'Devuelve las reservas futuras confirmadas del número de WhatsApp del cliente actual (día, hora, personas, zona y observaciones). Úsala cuando pregunte por su reserva o antes de modificar o cancelar.',
     {'accion': 'reservas_cliente', 'origen': 'whatsapp', 'telefono_cliente': C}, '[320, 420]'),
    ('tModificar', 'Modificar reserva', 'Cambia el día, la hora, las personas, la zona o las observaciones de una reserva del cliente actual. La reserva se identifica por su día y hora actuales. Comprueba la disponibilidad; si no hay sitio, la reserva original se mantiene y devuelve alternativas. Úsala solo tras confirmación explícita.',
     {'accion': 'modificar', 'origen': 'whatsapp', 'telefono_cliente': C,
      'reserva_ref': fa('reserva_actual', 'Día y hora de la reserva actual en formato YYYY-MM-DD HH:MM (tal como la devuelve "Ver reservas del cliente"). Vacío si el cliente solo tiene una reserva'),
      'fecha': fa('fecha', 'Nueva fecha YYYY-MM-DD, o vacío para mantener la actual'), 'hora': fa('hora', 'Nueva hora HH:MM, o vacío para mantener la actual'),
      'personas': fa('personas', 'Nuevo número de comensales, o 0 para mantener el actual', 'number'), 'zona': fa('zona', 'Interior o Terraza, o vacío para mantener la actual o si da igual'),
      'observaciones': fa('observaciones', 'Nuevas observaciones, o vacío para mantener las actuales')}, '[480, 420]'),
    ('tCancelar', 'Cancelar reserva', 'Cancela una reserva del cliente actual (identificada por su día y hora). Úsala solo tras confirmación explícita.',
     {'accion': 'cancelar', 'origen': 'whatsapp', 'telefono_cliente': C,
      'reserva_ref': fa('reserva_actual', 'Día y hora de la reserva actual en formato YYYY-MM-DD HH:MM (tal como la devuelve "Ver reservas del cliente"). Vacío si el cliente solo tiene una reserva')}, '[640, 420]'),
]

which = sys.argv[1]
if which == 'secretario':
    out = agente_wf('secretario', 'Reservas · Secretario interno', 'Secretario', 'prompts/secretario.md',
                    "Personal: {{ $('Entrada').first().json.nombre_perfil }} (tel. {{ $('Entrada').first().json.telefono }})",
                    secretario_tools, "={{ 'sec-' + " + TEL + " }}",
                    '⚠️ No he podido completar la petición por un problema técnico. No se ha cambiado nada; inténtalo de nuevo en un momento.',
                    '## Secretario interno\nSolo llega aquí quien está en `res_personal` con activo=true (lo decide el enrutador). Sus herramientas llaman al **Motor común** con origen=secretario y el teléfono real del remitente: el motor vuelve a comprobar el rol (lectura / gestion / admin) antes de cada acción.\nMemoria separada por persona (clave `sec-<teléfono>`). Las reservas NO se guardan en la memoria: siempre se consultan en las Data Tables.', '')
else:
    out = agente_wf('chatbot-clientes', 'Reservas · Chatbot clientes WhatsApp', 'Asistente del restaurante', 'prompts/cliente.md',
                    "Cliente: {{ $('Entrada').first().json.nombre_perfil || 'desconocido' }}\nTeléfono: {{ $('Entrada').first().json.telefono }}",
                    cliente_tools, '={{ ' + TEL + ' }}',
                    'Lo siento 🙏 ahora mismo no puedo atenderte por un problema técnico. Puedes llamarnos al *+34 931 234 567* 📞',
                    '## Chatbot de clientes (WhatsApp)\nMismo asistente, FAQ y tono que el chatbot original. Lo único que cambia: sus herramientas llaman al **Motor común** (Data Tables) con origen=whatsapp y el teléfono del remitente puesto por el sistema (la IA no puede cambiarlo).\nMemoria por número de cliente.', '')
open(sys.argv[2], 'w').write(out)
