from common import *
vals = {n: ('={{ $json.body.%s ?? 0 }}' % n if t == 'number' else '={{ $json.body.%s ?? "" }}' % n) for n, t in ENTRADAS_MOTOR}
print(f"""import {{ workflow, node, trigger, sticky, expr }} from '@n8n/workflow-sdk';
const wh = trigger({{ type: 'n8n-nodes-base.webhook', version: 2.1, config: {{ name: 'Petición de prueba', position: [0, 0], parameters: {{ httpMethod: 'POST', path: 'reservas-banco-pruebas', responseMode: 'lastNode', options: {{}} }} }}, output: [{{ body: {{ accion: 'listar' }} }}] }});
const motor = node({{ type: 'n8n-nodes-base.executeWorkflow', version: 1.4, config: {{ name: 'Llamar al motor', position: [260, 0], parameters: {{ mode: 'once', source: 'database', workflowId: {motor_rl()}, workflowInputs: {llamar_motor(vals)}, options: {{ waitForSubWorkflow: true }} }} }}, output: [{{ resultado: {{ ok: true }} }}] }});
const nota = sticky('## Banco de pruebas del motor\\nSolo para pruebas manuales (mantener **inactivo**). Recibe en el body los mismos campos que el motor (accion, origen, actor_telefono, telefono_cliente...).', [wh, motor], {{ color: 3 }});
export default workflow('banco', 'Reservas · Banco de pruebas (no activar)').add(wh).to(motor).add(nota);""")
