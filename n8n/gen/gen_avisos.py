import sys
from common import *

SELF_ID = sys.argv[1] if len(sys.argv) > 1 else ''
WA = "{ whatsAppApi: { id: 'FHP0FshdNlUEHKuI', name: 'WhatsApp account' } }"
GCAL = "{ googleCalendarOAuth2Api: { id: 'FP2UZXDO80bSTWrw', name: 'Google Calendar account' } }"
P = "$('Preparar aviso y calendario').first().json"
code_prep = lib_code('avisos/preparar.js')
code_res = lib_code('avisos/resultado_aviso.js')
code_cal = lib_code('avisos/estado_calendario.js')


def upd_evento(var, nombre, cols, pos, id_expr='={{ $json.evento_id }}'):
    vals = ', '.join(f"{J(k)}: {E(v)}" for k, v in cols.items())
    schema = ', '.join(f"{{ id: {J(k)}, displayName: {J(k)}, required: false, defaultMatch: false, display: true, type: 'string', canBeUsedToMatch: true }}" for k in cols)
    return f"""const {var} = node({{ type: 'n8n-nodes-base.dataTable', version: 1.1, config: {{ name: {J(nombre)}, alwaysOutputData: true, onError: 'continueRegularOutput', position: {pos},
  parameters: {{ resource: 'row', operation: 'update', dataTableId: {tabla('res_eventos')}, matchType: 'allConditions', filters: {condiciones([('id', 'eq', id_expr)])},
  columns: {{ mappingMode: 'defineBelow', value: {{ {vals} }}, matchingColumns: [], schema: [ {schema} ], attemptToConvertTypes: false, convertFieldsToString: false }} }} }}, output: [{{ id: 1 }}] }});"""


def http(var, nombre, method, url, pos, body=None):
    b = f", sendBody: true, specifyBody: 'json', jsonBody: {E(body)}" if body else ''
    return f"""const {var} = node({{ type: 'n8n-nodes-base.httpRequest', version: 4.3, config: {{ name: {J(nombre)}, onError: 'continueRegularOutput', alwaysOutputData: true, position: {pos}, credentials: {GCAL},
  parameters: {{ method: {J(method)}, url: {E(url)}, authentication: 'predefinedCredentialType', nodeCredentialType: 'googleCalendarOAuth2Api'{b}, options: {{}} }} }}, output: [{{ id: 'abc' }}] }});"""


def sw(var, nombre, campo, claves, pos):
    rules = ', '.join(
        f"{{ outputKey: {J(k)}, renameOutput: true, conditions: {{ options: {{ caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 }}, conditions: [ {{ leftValue: {E(campo)}, operator: {{ type: 'string', operation: 'equals' }}, rightValue: {J(k)} }} ], combinator: 'and' }} }}"
        for k in claves)
    return f"const {var} = switchCase({{ version: 3.2, config: {{ name: {J(nombre)}, position: {pos}, parameters: {{ rules: {{ values: [ {rules} ] }}, options: {{}} }} }} }});"


buscar_url = "=https://www.googleapis.com/calendar/v3/calendars/{{ encodeURIComponent(" + P + ".cal.cal_anterior) }}/events?maxResults=5&privateExtendedProperty={{ encodeURIComponent('codigo=' + " + P + ".codigo) }}"
borrar_url = "=https://www.googleapis.com/calendar/v3/calendars/{{ encodeURIComponent(" + P + ".cal.cal_anterior) }}/events/{{ $json.items?.[0]?.id ?? 'ninguno' }}?sendUpdates=none"
crear_url = "=https://www.googleapis.com/calendar/v3/calendars/{{ encodeURIComponent(" + P + ".cal.cal_nuevo) }}/events?sendUpdates=none"

reintento = ''
reintento_chain = ''
if SELF_ID:
    reintento = f"""const cada30 = trigger({{ type: 'n8n-nodes-base.scheduleTrigger', version: 1.3, config: {{ name: 'Reintentar pendientes cada 30 min', position: [0, 760], parameters: {{ rule: {{ interval: [ {{ field: 'minutes', minutesInterval: 30 }} ] }} }} }}, output: [{{}}] }});
const pendientes = node({{ type: 'n8n-nodes-base.dataTable', version: 1.1, config: {{ name: 'Eventos de las últimas 6 h', position: [220, 760], parameters: {{ resource: 'row', operation: 'get', dataTableId: {tabla('res_eventos')}, matchType: 'allConditions', filters: {condiciones([('ts', 'gte', '={{ $now.minus({ hours: 6 }).toMillis() }}'), ('ts', 'lte', '={{ $now.minus({ minutes: 3 }).toMillis() }}')])}, returnAll: true }} }}, output: [{{ id: 1 }}] }});
const soloPendientes = node({{ type: 'n8n-nodes-base.filter', version: 2.2, config: {{ name: 'Solo con aviso o calendario pendiente', position: [440, 760], parameters: {{ conditions: {{ options: {{ caseSensitive: true, leftValue: '', typeValidation: 'loose', version: 2 }}, conditions: [ {{ leftValue: expr('{{{{ $json.aviso_estado === "pendiente" || $json.calendario_estado === "pendiente" }}}}'), operator: {{ type: 'boolean', operation: 'true', singleValue: true }} }} ], combinator: 'and' }}, options: {{}} }} }}, output: [{{ id: 1 }}] }});
const relanzar = node({{ type: 'n8n-nodes-base.executeWorkflow', version: 1.4, config: {{ name: 'Procesar de nuevo', position: [660, 760], parameters: {{ mode: 'each', source: 'database', workflowId: {{ __rl: true, mode: 'id', value: {J(SELF_ID)} }}, workflowInputs: {{ mappingMode: 'defineBelow', value: {{ evento_id: expr('{{{{ $json.id }}}}') }}, matchingColumns: [], schema: [ {{ id: 'evento_id', displayName: 'evento_id', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true, type: 'number' }} ], attemptToConvertTypes: false }}, options: {{ waitForSubWorkflow: false }} }} }}, output: [{{}}] }});"""
    reintento_chain = ".add(cada30).to(pendientes).to(soloPendientes).to(relanzar)"

sdk = f"""import {{ workflow, node, trigger, sticky, ifElse, switchCase, expr }} from '@n8n/workflow-sdk';

const entrada = trigger({{ type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2, config: {{ name: 'Entrada', position: [0, 300], parameters: {{ inputSource: 'workflowInputs', workflowInputs: {{ values: [ {{ name: 'evento_id', type: 'number' }} ] }} }} }}, output: [{{ evento_id: 1 }}] }});
const leerEvento = node({{ type: 'n8n-nodes-base.dataTable', version: 1.1, config: {{ name: 'Leer evento', position: [220, 300], parameters: {{ resource: 'row', operation: 'get', dataTableId: {tabla('res_eventos')}, matchType: 'allConditions', filters: {condiciones([('id', 'eq', '={{ $json.evento_id }}')])}, limit: 1 }} }}, output: [{{ id: 1, tipo: 'creada' }}] }});
const leerConfig = node({{ type: 'n8n-nodes-base.dataTable', version: 1.1, config: {{ name: 'Leer configuración', alwaysOutputData: true, executeOnce: true, position: [440, 300], parameters: {{ resource: 'row', operation: 'get', dataTableId: {tabla('res_config')}, returnAll: true }} }}, output: [{{ id: 1 }}] }});
const leerPersonal = node({{ type: 'n8n-nodes-base.dataTable', version: 1.1, config: {{ name: 'Leer personal', alwaysOutputData: true, executeOnce: true, position: [660, 300], parameters: {{ resource: 'row', operation: 'get', dataTableId: {tabla('res_personal')}, returnAll: true }} }}, output: [{{ id: 1 }}] }});
const preparar = node({{ type: 'n8n-nodes-base.code', version: 2, config: {{ name: 'Preparar aviso y calendario', position: [880, 300], parameters: {{ jsCode: {J(code_prep)} }} }}, output: [{{ evento_id: 1, hay_aviso: true, destinatarios: [], cal: {{ accion: 'nada' }} }}] }});

const hayAviso = ifElse({{ version: 2.2, config: {{ name: '¿Avisar al personal?', position: [1100, 140], parameters: {cond_if('{{ $json.hay_aviso }}', 'boolean', 'true')} }} }});
const separar = node({{ type: 'n8n-nodes-base.splitOut', version: 1, config: {{ name: 'Un aviso por persona', position: [1320, 40], parameters: {{ fieldToSplitOut: 'destinatarios', options: {{}} }} }}, output: [{{ telefono: '346', nombre: 'x' }}] }});
const enviar = node({{ type: 'n8n-nodes-base.whatsApp', version: 1.1, config: {{ name: 'Enviar aviso por WhatsApp', onError: 'continueRegularOutput', position: [1540, 40], credentials: {WA},
  parameters: {{ operation: 'send', phoneNumberId: {E("={{ " + P + ".phone_number_id }}")}, recipientPhoneNumber: {E('={{ $json.telefono }}')}, textBody: {E("={{ " + P + ".texto }}")}, additionalFields: {{}} }} }}, output: [{{ messages: [{{ id: 'wamid' }}] }}] }});
const resultadoAviso = node({{ type: 'n8n-nodes-base.code', version: 2, config: {{ name: 'Resultado del aviso', position: [1760, 40], parameters: {{ jsCode: {J(code_res)} }} }}, output: [{{ evento_id: 1, aviso_estado: 'enviado' }}] }});
{upd_evento('anotarAviso', 'Anotar estado del aviso', {'aviso_estado': '={{ $json.aviso_estado }}', 'aviso_detalle': '={{ $json.aviso_detalle }}'}, '[1980, 40]')}
const hayMotivo = ifElse({{ version: 2.2, config: {{ name: '¿Aviso imposible?', position: [1320, 220], parameters: {cond_if('{{ $json.aviso_estado_previo }}', 'string', 'notEmpty')} }} }});
{upd_evento('anotarSinAviso', 'Anotar aviso no enviado', {'aviso_estado': '={{ $json.aviso_estado_previo }}', 'aviso_detalle': '={{ $json.aviso_detalle_previo }}'}, '[1540, 220]')}

{sw('segunCal', 'Acción en calendario', '{{ $json.cal.accion }}', ['crear', 'reemplazar', 'borrar', 'no_configurado'], '[1100, 520]')}
{http('buscarAnt', 'Buscar evento anterior', 'GET', buscar_url, '[1320, 520]')}
{http('borrarAnt', 'Borrar evento anterior', 'DELETE', borrar_url, '[1540, 520]')}
{http('crearEv', 'Crear evento en calendario', 'POST', crear_url, '[1760, 420]', "={{ JSON.stringify(" + P + ".cal.cuerpo) }}")}
{http('buscarCanc', 'Buscar evento cancelado', 'GET', buscar_url, '[1320, 680]')}
{http('borrarCanc', 'Borrar evento cancelado', 'DELETE', borrar_url, '[1540, 680]')}
const estadoCal = node({{ type: 'n8n-nodes-base.code', version: 2, config: {{ name: 'Estado del calendario', position: [1980, 520], parameters: {{ jsCode: {J(code_cal)} }} }}, output: [{{ evento_id: 1, calendario_estado: 'ok' }}] }});
{upd_evento('anotarCal', 'Anotar estado del calendario', {'calendario_estado': '={{ $json.calendario_estado }}'}, '[2200, 520]')}
{upd_evento('anotarNoCal', 'Anotar calendario no configurado', {'calendario_estado': 'no_configurado'}, '[1320, 840]')}
{reintento}

const nota = sticky('## Avisos y calendario\\nSe lanza (sin esperar) después de que el motor GUARDA un cambio. Envía el aviso de WhatsApp al personal con `recibe_avisos` y copia la reserva en Google Calendar.\\n**Separación:** un fallo aquí NO deshace ni repite la reserva; solo queda anotado en `res_eventos` (aviso_estado / calendario_estado) y se reintenta cada 30 min.\\nCuándo se avisa (lo decide el motor): reservas de clientes para HOY, grupos grandes (`aviso_grupo_desde`), cancelaciones de hoy/mañana, llamadas que piden una persona y errores.', [entrada, leerEvento, preparar], {{ color: 5 }});

export default workflow('avisos', 'Reservas · Avisos y calendario')
  .add(entrada).to(leerEvento).to(leerConfig).to(leerPersonal).to(preparar)
  .to(hayAviso.onTrue(separar.to(enviar).to(resultadoAviso).to(anotarAviso)).onFalse(hayMotivo.onTrue(anotarSinAviso)))
  .add(preparar).to(segunCal
    .onCase(0, crearEv)
    .onCase(1, buscarAnt.to(borrarAnt).to(crearEv))
    .onCase(2, buscarCanc.to(borrarCanc).to(estadoCal))
    .onCase(3, anotarNoCal))
  .add(crearEv).to(estadoCal).to(anotarCal)
  {reintento_chain}
  .add(nota);
"""
open(sys.argv[2], 'w').write(sdk)
