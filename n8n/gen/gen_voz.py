"""Webhook de herramientas para el agente telefónico (capa de voz en tiempo real externa, p. ej. ElevenLabs Agents)."""
import sys
from common import *

code_prep = lib_code('voz/preparar.js')
P = "$('Preparar petición').first().json"
motor_vals = {n: ("={{ " + P + ".motor." + n + " ?? 0 }}" if t == 'number' else "={{ " + P + ".motor." + n + " ?? '' }}")
              for n, t in ENTRADAS_MOTOR if n in ('accion', 'origen', 'telefono_cliente', 'nombre', 'fecha', 'hora', 'personas', 'zona', 'observaciones', 'reserva_ref')}
ev_cols = {
    'reserva_codigo': '', 'tipo': 'escalado', 'origen': 'llamada', 'actor': "={{ " + P + ".caller_id || 'número oculto' }}", 'antes': '',
    'despues': "={{ JSON.stringify(" + P + ".escalado) }}", 'ts': '={{ $now.toMillis() }}', 'avisar': True, 'aviso_estado': 'pendiente', 'aviso_detalle': '', 'calendario_estado': 'no_aplica'}


def sw_herr():
    reglas = [('calendario', "{{ " + P + ".herramienta === 'consultar_calendario' }}"),
              ('transferencia', "{{ " + P + ".herramienta === 'registrar_transferencia' }}"),
              ('reservas', "{{ !!" + P + ".accion }}")]
    rules = ', '.join(
        f"{{ outputKey: {J(k)}, renameOutput: true, conditions: {{ options: {{ caseSensitive: true, leftValue: '', typeValidation: 'loose', version: 2 }}, conditions: [ {{ leftValue: {E(c)}, operator: {{ type: 'boolean', operation: 'true', singleValue: true }} }} ], combinator: 'and' }} }}"
        for k, c in reglas)
    return f"const segunHerr = switchCase({{ version: 3.2, config: {{ name: 'Según herramienta', position: [880, 300], parameters: {{ rules: {{ values: [ {rules} ] }}, options: {{ fallbackOutput: 'extra', renameFallbackOutput: 'Desconocida' }} }} }} }});"


def resp(var, nombre, body, pos, code=None):
    c = f", options: {{ responseCode: {code} }}" if code else ", options: {}"
    return f"const {var} = node({{ type: 'n8n-nodes-base.respondToWebhook', version: 1.5, config: {{ name: {J(nombre)}, position: {pos}, parameters: {{ respondWith: 'json', responseBody: {E(body) if '{{' in body else J(body)}{c} }} }}, output: [{{}}] }});"


ev_vals = ', '.join(f"{J(k)}: {E(v) if isinstance(v, str) and '{{' in v else J(v)}" for k, v in ev_cols.items())
ev_schema = ', '.join(f"{{ id: {J(k)}, displayName: {J(k)}, required: false, defaultMatch: false, display: true, type: {J(COLUMNAS['res_eventos'][k])}, canBeUsedToMatch: true }}" for k in ev_cols)

sdk = f"""import {{ workflow, node, trigger, sticky, ifElse, switchCase, expr }} from '@n8n/workflow-sdk';
const wh = trigger({{ type: 'n8n-nodes-base.webhook', version: 2.1, config: {{ name: 'Llamada del agente de voz', position: [0, 300], parameters: {{ httpMethod: 'POST', path: 'reservas-voz', responseMode: 'responseNode', options: {{}} }} }}, output: [{{ headers: {{ 'x-clave': 'x' }}, body: {{ herramienta: 'consultar_disponibilidad', caller_id: '+34600000000' }} }}] }});
const leerClave = node({{ type: 'n8n-nodes-base.dataTable', version: 1.1, config: {{ name: 'Leer clave del agente de voz', position: [220, 300], alwaysOutputData: true, parameters: {{ resource: 'row', operation: 'get', dataTableId: {tabla('res_config')}, matchType: 'allConditions', filters: {condiciones([('clave', 'eq', 'clave_voz')])}, limit: 1 }} }}, output: [{{ valor: 'x' }}] }});
const claveOk = ifElse({{ version: 2.2, config: {{ name: '¿Petición autenticada?', position: [440, 300], parameters: {cond_if("{{ !!$json.valor && $json.valor === $('Llamada del agente de voz').first().json.headers['x-clave'] }}", 'boolean', 'true')} }} }});
{resp('noAuth', 'Rechazar (401)', '{ "error": "no autorizado" }', '[660, 480]', 401)}
const preparar = node({{ type: 'n8n-nodes-base.code', version: 2, config: {{ name: 'Preparar petición', position: [660, 300], parameters: {{ jsCode: {J(code_prep)} }} }}, output: [{{ herramienta: 'x', accion: 'disponibilidad', motor: {{}} }}] }});
{sw_herr()}
{resp('respCal', 'Devolver calendario', "={{ JSON.stringify({ ahora: " + P + ".ahora, calendario: " + P + ".calendario }) }}", '[1100, 100]')}
const regEscalado = node({{ type: 'n8n-nodes-base.dataTable', version: 1.1, config: {{ name: 'Registrar petición de persona', position: [1100, 260], parameters: {{ resource: 'row', operation: 'insert', dataTableId: {tabla('res_eventos')}, columns: {{ mappingMode: 'defineBelow', value: {{ {ev_vals} }}, matchingColumns: [], schema: [ {ev_schema} ], attemptToConvertTypes: false, convertFieldsToString: false }} }} }}, output: [{{ id: 1 }}] }});
const avisar = node({{ type: 'n8n-nodes-base.executeWorkflow', version: 1.4, config: {{ name: 'Avisar al personal', position: [1320, 260], onError: 'continueRegularOutput', alwaysOutputData: true, parameters: {{ mode: 'once', source: 'database', workflowId: {{ __rl: true, mode: 'id', value: 'MjdJ51wJEZu5IsFq', cachedResultName: 'Reservas · Avisos y calendario' }}, workflowInputs: {{ mappingMode: 'defineBelow', value: {{ evento_id: expr('{{{{ $json.id }}}}') }}, matchingColumns: [], schema: [ {{ id: 'evento_id', displayName: 'evento_id', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true, type: 'number' }} ], attemptToConvertTypes: false }}, options: {{ waitForSubWorkflow: false }} }} }}, output: [{{}}] }});
{resp('respEsc', 'Confirmar registro', '{ "ok": true, "detalle": "Aviso registrado. Ahora transfiere la llamada con la herramienta de transferencia." }', '[1540, 260]')}
const motor = node({{ type: 'n8n-nodes-base.executeWorkflow', version: 1.4, config: {{ name: 'Llamar al motor', position: [1100, 440], parameters: {{ mode: 'once', source: 'database', workflowId: {motor_rl()}, workflowInputs: {llamar_motor(motor_vals, True)}, options: {{ waitForSubWorkflow: true }} }} }}, output: [{{ resultado: {{ ok: true }} }}] }});
{resp('respMotor', 'Devolver resultado', '={{ JSON.stringify($json.resultado) }}', '[1320, 440]')}
{resp('respDesc', 'Herramienta desconocida', '{ "ok": false, "motivo": "herramienta_desconocida" }', '[1100, 600]', 400)}
const nota = sticky('## Herramientas del agente telefónico\\nLa voz en tiempo real la pone el proveedor (recomendado: ElevenLabs Agents + número Twilio/SIP). Sus *server tools* llaman aquí (POST /webhook/reservas-voz, cabecera `x-clave` = res_config.clave_voz).\\n- consultar_disponibilidad · crear_reserva · ver_mis_reservas · modificar_reserva · cancelar_reserva → **Motor común** (origen=llamada).\\n- Ver/modificar/cancelar SOLO con el número que llama (caller ID). Con número oculto → transferir.\\n- registrar_transferencia → aviso al personal; la transferencia la hace el proveedor (transfer_to_number).\\n- consultar_calendario → fecha de hoy y próximos días (Europe/Madrid).', [wh, preparar, motor], {{ color: 4 }});
export default workflow('voz', 'Reservas · Herramientas agente telefónico')
  .add(wh).to(leerClave).to(claveOk.onTrue(preparar.to(segunHerr
    .onCase(0, respCal)
    .onCase(1, regEscalado.to(avisar).to(respEsc))
    .onCase(2, motor.to(respMotor))
    .onCase(3, respDesc))).onFalse(noAuth))
  .add(nota);
"""
open(sys.argv[1], 'w').write(sdk)
