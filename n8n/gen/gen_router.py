"""Enrutador único de WhatsApp: anti-duplicados, identificación del remitente, audio -> texto y reparto cliente/secretario."""
import sys
from common import *

SECRETARIO_ID = 'RISmUsfFDEmfPzUL'
CLIENTES_ID = 'xDiHbTj31JLz7JO2'
WA = "{ whatsAppApi: { id: 'FHP0FshdNlUEHKuI', name: 'WhatsApp account' } }"
WAT = "{ whatsAppTriggerApi: { id: '2YlzCNfjLjFSUWay', name: 'WhatsApp OAuth account' } }"
OPENAI = "{ openAiApi: { id: 'sBeNn2zvBvjvV7Ci', name: 'OpenAI account' } }"
M = "$('Identificar remitente').first().json"

code_ident = """// Une el mensaje normalizado con la ficha de personal (si existe). Solo cuenta como personal quien está activo.
const m = $('Mensaje').first().json;
const tel = String(m.telefono || '').replace(/\\D/g, '');
const p = $input.all().map(i => i.json).find(j => j && j.id && String(j.telefono || '').replace(/\\D/g, '') === tel && (j.activo === true || j.activo === 'true'));
return [{ json: { ...m, telefono: tel, es_personal: !!p, rol: p ? String(p.rol || '') : '', nombre_personal: p ? String(p.nombre || '') : '' } }];
"""
code_primero = """// Anti-duplicados: WhatsApp puede reenviar el mismo webhook. Solo sigue la ejecución que registró PRIMERO este wamid.
const mio = Number($('Registrar mensaje').first().json.id);
const ids = $input.all().map(i => Number(i.json.id)).filter(n => !isNaN(n) && n > 0);
return [{ json: { primero: ids.length > 0 && Math.min(...ids) === mio, registros: ids.length } }];
"""


def setn(var, nombre, asig, pos, extra=''):
    return f"const {var} = node({{ type: 'n8n-nodes-base.set', version: 3.4, config: {{ name: {J(nombre)}, position: {pos}{extra}, parameters: {set_fields(asig)} }}, output: [{{ texto: 'x' }}] }});"


def subwf(var, nombre, wid, wname, pos):
    vals = {'texto': '={{ $json.texto }}', 'telefono': '={{ ' + M + '.telefono }}', 'nombre_perfil': '={{ ' + M + '.nombre_personal || ' + M + '.nombre_perfil }}', 'tipo_mensaje': '={{ $json.tipo_mensaje }}'}
    v = ', '.join(f"{J(k)}: {E(x)}" for k, x in vals.items())
    sc = ', '.join(f"{{ id: {J(k)}, displayName: {J(k)}, required: false, defaultMatch: false, display: true, canBeUsedToMatch: true, type: 'string' }}" for k in vals)
    return f"""const {var} = node({{ type: 'n8n-nodes-base.executeWorkflow', version: 1.4, config: {{ name: {J(nombre)}, position: {pos},
  parameters: {{ mode: 'once', source: 'database', workflowId: {{ __rl: true, mode: 'id', value: {J(wid)}, cachedResultName: {J(wname)} }}, workflowInputs: {{ mappingMode: 'defineBelow', value: {{ {v} }}, matchingColumns: [], schema: [ {sc} ], attemptToConvertTypes: false, convertFieldsToString: false }}, options: {{ waitForSubWorkflow: true }} }} }}, output: [{{ respuesta: 'texto' }}] }});"""


def sw(var, nombre, reglas, pos):
    rules = ', '.join(
        f"{{ outputKey: {J(k)}, renameOutput: true, conditions: {{ options: {{ caseSensitive: true, leftValue: '', typeValidation: 'loose', version: 2 }}, conditions: [ {{ leftValue: {E(cond)}, operator: {{ type: 'boolean', operation: 'true', singleValue: true }} }} ], combinator: 'and' }} }}"
        for k, cond in reglas)
    return f"const {var} = switchCase({{ version: 3.2, config: {{ name: {J(nombre)}, position: {pos}, parameters: {{ rules: {{ values: [ {rules} ] }}, options: {{ fallbackOutput: 'extra', renameFallbackOutput: 'Otro' }} }} }} }});"


norm_wa = [('es_prueba', 'boolean', False), ('telefono', 'string', '={{ $json.messages[0].from }}'), ('wamid', 'string', '={{ $json.messages[0].id }}'),
           ('tipo', 'string', '={{ $json.messages[0].type }}'), ('texto', 'string', '={{ $json.messages[0].text?.body ?? $json.messages[0].image?.caption ?? $json.messages[0].video?.caption ?? "" }}'),
           ('audio_id', 'string', '={{ $json.messages[0].audio?.id ?? "" }}'), ('audio_texto_prueba', 'string', ''),
           ('nombre_perfil', 'string', '={{ $json.contacts?.[0]?.profile?.name ?? "" }}'), ('phone_number_id', 'string', '={{ $json.metadata.phone_number_id }}')]
B = "$('Entrada de pruebas').first().json.body"
norm_pr = [('es_prueba', 'boolean', True), ('telefono', 'string', '={{ String(' + B + '.telefono ?? "") }}'), ('wamid', 'string', '={{ ' + B + '.wamid || ("prueba-" + $execution.id) }}'),
           ('tipo', 'string', '={{ ' + B + '.tipo || "text" }}'), ('texto', 'string', '={{ ' + B + '.texto ?? "" }}'), ('audio_id', 'string', ''),
           ('audio_texto_prueba', 'string', '={{ ' + B + '.audio_texto ?? "" }}'), ('nombre_perfil', 'string', '={{ ' + B + '.nombre ?? "Prueba" }}'), ('phone_number_id', 'string', '')]


def set_raw(var, nombre, asig, pos):
    a = ', '.join(f"{{ id: {J('a-' + n)}, name: {J(n)}, type: {J(t)}, value: {E(v) if isinstance(v, str) and '{{' in v else J(v)} }}" for n, t, v in asig)
    return f"const {var} = node({{ type: 'n8n-nodes-base.set', version: 3.4, config: {{ name: {J(nombre)}, position: {pos}, parameters: {{ assignments: {{ assignments: [ {a} ] }}, options: {{}} }} }}, output: [{{ telefono: '34', wamid: 'w', tipo: 'text', texto: 'hola', es_prueba: false }}] }});"


ins_msg = columnas('res_mensajes', {'wamid': '={{ $json.wamid }}', 'canal': '={{ $json.es_prueba ? "prueba" : "whatsapp" }}', 'telefono': '={{ $json.telefono }}', 'recibido_ts': '={{ $now.toMillis() }}'})

sdk = f"""import {{ workflow, node, trigger, sticky, ifElse, switchCase, expr }} from '@n8n/workflow-sdk';

const waTrigger = trigger({{ type: 'n8n-nodes-base.whatsAppTrigger', version: 1, config: {{ name: 'Mensaje de WhatsApp recibido', position: [0, 200], credentials: {WAT}, parameters: {{ updates: ['messages'], options: {{}} }} }}, output: [{{ messages: [{{ from: '34', id: 'wamid', type: 'text', text: {{ body: 'hola' }} }}], contacts: [{{ profile: {{ name: 'x' }} }}], metadata: {{ phone_number_id: '1' }} }}] }});
const soloMensajes = node({{ type: 'n8n-nodes-base.filter', version: 2.2, config: {{ name: 'Solo mensajes (no estados)', position: [220, 200], parameters: {{ conditions: {{ options: {{ caseSensitive: true, leftValue: '', typeValidation: 'loose', version: 2 }}, conditions: [ {{ leftValue: expr('{{{{ $json.messages?.[0]?.id ?? "" }}}}'), operator: {{ type: 'string', operation: 'notEmpty', singleValue: true }} }} ], combinator: 'and' }}, options: {{}} }} }}, output: [{{}}] }});
{set_raw('normWa', 'Normalizar WhatsApp', norm_wa, '[440, 200]')}
const guardarPhoneId = node({{ type: 'n8n-nodes-base.dataTable', version: 1.1, config: {{ name: 'Recordar phone_number_id', position: [660, 40], onError: 'continueRegularOutput', alwaysOutputData: true,
  parameters: {{ resource: 'row', operation: 'update', dataTableId: {tabla('res_config')}, matchType: 'allConditions', filters: {condiciones([('clave', 'eq', 'whatsapp_phone_number_id')])},
  columns: {{ mappingMode: 'defineBelow', value: {{ valor: expr('{{{{ $json.phone_number_id }}}}') }}, matchingColumns: [], schema: [ {{ id: 'valor', displayName: 'valor', required: false, defaultMatch: false, display: true, type: 'string', canBeUsedToMatch: true }} ], attemptToConvertTypes: false, convertFieldsToString: false }} }} }}, output: [{{ id: 1 }}] }});

const whPrueba = trigger({{ type: 'n8n-nodes-base.webhook', version: 2.1, config: {{ name: 'Entrada de pruebas', position: [0, 520], parameters: {{ httpMethod: 'POST', path: 'reservas-whatsapp-pruebas', responseMode: 'responseNode', options: {{}} }} }}, output: [{{ body: {{ clave: 'x', telefono: '34', texto: 'hola' }} }}] }});
const leerClave = node({{ type: 'n8n-nodes-base.dataTable', version: 1.1, config: {{ name: 'Leer clave de pruebas', position: [220, 520], alwaysOutputData: true, parameters: {{ resource: 'row', operation: 'get', dataTableId: {tabla('res_config')}, matchType: 'allConditions', filters: {condiciones([('clave', 'eq', 'clave_pruebas')])}, limit: 1 }} }}, output: [{{ valor: 'x' }}] }});
const claveOk = ifElse({{ version: 2.2, config: {{ name: '¿Clave correcta?', position: [440, 520], parameters: {cond_if("{{ !!$json.valor && $json.valor === " + B + ".clave }}", 'boolean', 'true')} }} }});
{set_raw('normPr', 'Normalizar prueba', norm_pr, '[660, 440]')}
const denegar = node({{ type: 'n8n-nodes-base.respondToWebhook', version: 1.5, config: {{ name: 'Rechazar (403)', position: [660, 620], parameters: {{ respondWith: 'json', responseBody: '{{ "error": "no autorizado" }}', options: {{ responseCode: 403 }} }} }}, output: [{{}}] }});

const mensaje = node({{ type: 'n8n-nodes-base.set', version: 3.4, config: {{ name: 'Mensaje', position: [880, 300], parameters: {{ includeOtherFields: true, assignments: {{ assignments: [] }}, options: {{}} }} }}, output: [{{ telefono: '34', wamid: 'w' }}] }});
const registrar = node({{ type: 'n8n-nodes-base.dataTable', version: 1.1, config: {{ name: 'Registrar mensaje', position: [1100, 300], parameters: {{ resource: 'row', operation: 'insert', dataTableId: {tabla('res_mensajes')}, columns: {ins_msg} }} }}, output: [{{ id: 1, wamid: 'w' }}] }});
const mismos = node({{ type: 'n8n-nodes-base.dataTable', version: 1.1, config: {{ name: 'Mismo mensaje ya recibido', position: [1320, 300], parameters: {{ resource: 'row', operation: 'get', dataTableId: {tabla('res_mensajes')}, matchType: 'allConditions', filters: {condiciones([('wamid', 'eq', "={{ $('Mensaje').first().json.wamid }}")])}, returnAll: true }} }}, output: [{{ id: 1 }}] }});
const primero = node({{ type: 'n8n-nodes-base.code', version: 2, config: {{ name: '¿Es la primera vez?', position: [1540, 300], parameters: {{ jsCode: {J(code_primero)} }} }}, output: [{{ primero: true }}] }});
const esPrimero = ifElse({{ version: 2.2, config: {{ name: '¿Procesar?', position: [1760, 300], parameters: {cond_if('{{ $json.primero }}', 'boolean', 'true')} }} }});
const dupPrueba = ifElse({{ version: 2.2, config: {{ name: '¿Duplicado en prueba?', position: [1980, 480], parameters: {cond_if("{{ $('Mensaje').first().json.es_prueba }}", 'boolean', 'true')} }} }});
const respDup = node({{ type: 'n8n-nodes-base.respondToWebhook', version: 1.5, config: {{ name: 'Responder duplicado (prueba)', position: [2200, 480], parameters: {{ respondWith: 'json', responseBody: '{{ "duplicado": true, "detalle": "Mensaje repetido: no se procesa otra vez" }}', options: {{}} }} }}, output: [{{}}] }});
const leerPersonal = node({{ type: 'n8n-nodes-base.dataTable', version: 1.1, config: {{ name: 'Buscar en personal', position: [1980, 200], alwaysOutputData: true, parameters: {{ resource: 'row', operation: 'get', dataTableId: {tabla('res_personal')}, matchType: 'allConditions', filters: {condiciones([('telefono', 'eq', "={{ $('Mensaje').first().json.telefono }}")])}, returnAll: true }} }}, output: [{{ id: 1 }}] }});
const ident = node({{ type: 'n8n-nodes-base.code', version: 2, config: {{ name: 'Identificar remitente', position: [2200, 200], parameters: {{ jsCode: {J(code_ident)} }} }}, output: [{{ es_personal: false, telefono: '34', tipo: 'text', texto: 'hola' }}] }});
{sw('porTipo', 'Tipo de mensaje', [('Audio', '{{ $json.tipo === "audio" && !!$json.audio_id }}'), ('Audio de prueba', '{{ $json.tipo === "audio" && !!$json.audio_texto_prueba }}'), ('Texto', '{{ $json.tipo === "text" }}')], '[2420, 200]')}
const urlAudio = node({{ type: 'n8n-nodes-base.whatsApp', version: 1.1, config: {{ name: 'Obtener URL del audio', position: [2640, 0], credentials: {WA}, parameters: {{ resource: 'media', operation: 'mediaUrlGet', mediaGetId: expr('{{{{ $json.audio_id }}}}') }} }}, output: [{{ url: 'https://x' }}] }});
const bajarAudio = node({{ type: 'n8n-nodes-base.httpRequest', version: 4.3, config: {{ name: 'Descargar audio', position: [2860, 0], credentials: {WA}, parameters: {{ url: expr('{{{{ $json.url }}}}'), authentication: 'predefinedCredentialType', nodeCredentialType: 'whatsAppApi', options: {{ response: {{ response: {{ responseFormat: 'file' }} }} }} }} }}, output: [{{}}] }});
const ttsPrueba = node({{ type: '@n8n/n8n-nodes-langchain.openAi', version: 2.3, config: {{ name: 'Generar nota de voz de prueba', position: [2860, 160], credentials: {OPENAI}, parameters: {{ resource: 'audio', operation: 'generate', model: 'tts-1', input: expr('{{{{ $json.audio_texto_prueba }}}}'), voice: 'nova', options: {{ response_format: 'mp3' }} }} }}, output: [{{}}] }});
const transcribir = node({{ type: '@n8n/n8n-nodes-langchain.openAi', version: 2.3, config: {{ name: 'Transcribir audio', position: [3080, 80], credentials: {OPENAI}, parameters: {{ resource: 'audio', operation: 'transcribe', options: {{}} }} }}, output: [{{ text: 'hola' }}] }});
{setn('txtAudio', 'Texto del audio', [('texto', 'string', '={{ $json.text }}'), ('tipo_mensaje', 'string', 'nota de voz transcrita')], '[3300, 80]')}
{setn('txtTexto', 'Texto escrito', [('texto', 'string', '={{ $json.texto }}'), ('tipo_mensaje', 'string', 'texto')], '[2640, 300]')}
{setn('txtOtro', 'Otro tipo de mensaje', [('texto', 'string', '={{ "[Ha enviado un mensaje de tipo " + $json.tipo + " que no es texto ni audio. " + ($json.texto || "") + "]" }}'), ('tipo_mensaje', 'string', '={{ $json.tipo }}')], '[2640, 460]')}
const esPersonal = ifElse({{ version: 2.2, config: {{ name: '¿Personal autorizado?', position: [3520, 300], parameters: {cond_if("{{ " + M + ".es_personal }}", 'boolean', 'true')} }} }});
{subwf('aSecretario', 'Secretario interno', SECRETARIO_ID, 'Reservas · Secretario interno', '[3740, 200]')}
{subwf('aClientes', 'Chatbot de clientes', CLIENTES_ID, 'Reservas · Chatbot clientes WhatsApp', '[3740, 400]')}
{setn('respFinal', 'Respuesta final', [('respuesta', 'string', '={{ $json.respuesta }}'), ('ruta', 'string', '={{ ' + M + '.es_personal ? "secretario (" + ' + M + '.rol + ")" : "cliente" }}'), ('texto_recibido', 'string', "={{ $('Texto escrito').isExecuted ? $('Texto escrito').first().json.texto : ($('Texto del audio').isExecuted ? $('Texto del audio').first().json.texto : '') }}")], '[3960, 300]')}
const esPrueba = ifElse({{ version: 2.2, config: {{ name: '¿Es una prueba?', position: [4180, 300], parameters: {cond_if("{{ " + M + ".es_prueba }}", 'boolean', 'true')} }} }});
const respPrueba = node({{ type: 'n8n-nodes-base.respondToWebhook', version: 1.5, config: {{ name: 'Devolver respuesta (prueba)', position: [4400, 200], parameters: {{ respondWith: 'json', responseBody: expr('{{{{ JSON.stringify({{ respuesta: $json.respuesta, ruta: $json.ruta, texto_recibido: $json.texto_recibido }}) }}}}'), options: {{}} }} }}, output: [{{}}] }});
const enviar = node({{ type: 'n8n-nodes-base.whatsApp', version: 1.1, config: {{ name: 'Responder por WhatsApp', position: [4400, 400], credentials: {WA}, retryOnFail: true,
  parameters: {{ operation: 'send', phoneNumberId: {E("={{ " + M + ".phone_number_id }}")}, recipientPhoneNumber: {E("={{ " + M + ".telefono }}")}, textBody: expr('{{{{ $json.respuesta }}}}'), additionalFields: {{}} }} }}, output: [{{}}] }});

const nota = sticky('## Entrada única de WhatsApp\\nTodos los mensajes al número del restaurante entran aquí (solo puede haber UN disparador de WhatsApp activo por número).\\n1. **Anti-duplicados**: guarda el id del mensaje (wamid) en `res_mensajes`; si WhatsApp reenvía el mismo webhook, solo sigue la primera ejecución.\\n2. **Quién escribe**: si el teléfono está en `res_personal` con activo=true → *Secretario interno*; si no → *Chatbot de clientes*.\\n3. **Notas de voz**: se descargan y se transcriben (OpenAI) para ambos.\\n4. Responde por WhatsApp. La **Entrada de pruebas** (POST con `clave` = res_config.clave_pruebas) hace lo mismo pero devuelve la respuesta por HTTP y no envía nada.', [waTrigger, soloMensajes, normWa], {{ color: 4 }});

export default workflow('enrutador', 'Reservas · Entrada WhatsApp (enrutador)')
  .add(waTrigger).to(soloMensajes).to(normWa).to(mensaje)
  .add(normWa).to(guardarPhoneId)
  .add(whPrueba).to(leerClave).to(claveOk.onTrue(normPr.to(mensaje)).onFalse(denegar))
  .add(mensaje).to(registrar).to(mismos).to(primero).to(esPrimero
    .onTrue(leerPersonal.to(ident).to(porTipo
      .onCase(0, urlAudio.to(bajarAudio).to(transcribir))
      .onCase(1, ttsPrueba.to(transcribir))
      .onCase(2, txtTexto)
      .onCase(3, txtOtro)))
    .onFalse(dupPrueba.onTrue(respDup)))
  .add(transcribir).to(txtAudio).to(esPersonal)
  .add(txtTexto).to(esPersonal)
  .add(txtOtro).to(esPersonal)
  .add(esPersonal.onTrue(aSecretario.to(respFinal)).onFalse(aClientes.to(respFinal)))
  .add(respFinal).to(esPrueba.onTrue(respPrueba).onFalse(enviar))
  .add(nota);
"""
open(sys.argv[1], 'w').write(sdk)
