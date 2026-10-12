import sys
from common import *

ENTRADAS = [('accion', 'string'), ('origen', 'string'), ('actor_telefono', 'string'), ('telefono_cliente', 'string'), ('nombre', 'string'),
            ('fecha', 'string'), ('hora', 'string'), ('fecha_hasta', 'string'), ('hora_hasta', 'string'), ('personas', 'number'), ('zona', 'string'),
            ('observaciones', 'string'), ('reserva_ref', 'string'), ('franja', 'string'), ('texto_busqueda', 'string'), ('plazas', 'number'), ('motivo', 'string')]
AVISOS_WF = sys.argv[1] if len(sys.argv) > 1 else ''

SKELETON = len(sys.argv) > 3 and sys.argv[3] == 'skeleton'
code_eval = '// se carga aparte' if SKELETON else lib_code('motor/lib.js', 'motor/evaluar.js')
code_ver = '// se carga aparte' if SKELETON else lib_code('motor/lib.js', 'motor/verificar.js')
code_comp = lib_code('motor/comprobar.js')
PLAN = "$('Evaluar solicitud').first().json"
ins_fila = {k: f"={{{{ {PLAN}.fila.{k} }}}}" for k in COLUMNAS['res_reservas']}
upd_mod = {k: f"={{{{ {PLAN}.fila.{k} }}}}" for k in ['nombre', 'telefono', 'fecha', 'hora', 'inicio_ts', 'fin_ts', 'personas', 'zona', 'observaciones', 'clave_idem', 'version', 'actualizado_ts']}
upd_can = {k: f"={{{{ {PLAN}.fila.{k} }}}}" for k in ['estado', 'version', 'actualizado_ts']}
ins_cola = {k: f"={{{{ $json.cola.{k} }}}}" for k in COLUMNAS['res_cola']}
ins_cierre = {k: f"={{{{ $json.cierre.{k} }}}}" for k in COLUMNAS['res_cierres']}
ins_evento = {k: f"={{{{ $json.evento.{k} }}}}" for k in COLUMNAS['res_eventos']}
id_version = condiciones([('id', 'eq', f"={{{{ {PLAN}.reserva_id }}}}"), ('version', 'eq', f"={{{{ {PLAN}.version_actual }}}}")])

def dt_get(var, nombre, tabla_n, conds, pos, once=True):
    filt = f", matchType: 'allConditions', filters: {condiciones(conds)}" if conds else ''
    return f"""const {var} = node({{ type: 'n8n-nodes-base.dataTable', version: 1.1, config: {{ name: {J(nombre)}, alwaysOutputData: true, executeOnce: {str(once).lower()}, position: {pos},
  parameters: {{ resource: 'row', operation: 'get', dataTableId: {tabla(tabla_n)}{filt}, returnAll: true }} }}, output: [{{ id: 1 }}] }});"""

def dt_write(var, nombre, tabla_n, op, cols, pos, conds=None, extra=''):
    filt = f", matchType: 'allConditions', filters: {conds}" if conds else ''
    return f"""const {var} = node({{ type: 'n8n-nodes-base.dataTable', version: 1.1, config: {{ name: {J(nombre)}{extra}, position: {pos},
  parameters: {{ resource: 'row', operation: {J(op)}, dataTableId: {tabla(tabla_n)}{filt}, columns: {cols} }} }}, output: [{{ id: 1 }}] }});"""

def setn(var, nombre, asig, pos):
    return f"""const {var} = node({{ type: 'n8n-nodes-base.set', version: 3.4, config: {{ name: {J(nombre)}, position: {pos}, parameters: {set_fields(asig)} }}, output: [{{ resultado: {{ ok: true }} }}] }});"""

def code(var, nombre, js, pos):
    return f"""const {var} = node({{ type: 'n8n-nodes-base.code', version: 2, config: {{ name: {J(nombre)}, position: {pos}, parameters: {{ jsCode: {J(js)} }} }}, output: [{{ op: 'respuesta' }}] }});"""

switch_rules = ', '.join(
    f"{{ outputKey: {J(k)}, renameOutput: true, conditions: {{ options: {{ caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 }}, conditions: [ {{ leftValue: expr('{{{{ $json.op }}}}'), operator: {{ type: 'string', operation: 'equals' }}, rightValue: {J(k)} }} ], combinator: 'and' }} }}"
    for k in ['respuesta', 'reservar', 'cancelar', 'bloquear', 'desbloquear'])

aviso_node = ''
aviso_chain = 'resGuardado'
if AVISOS_WF:
    aviso_node = f"""const lanzarAvisos = node({{ type: 'n8n-nodes-base.executeWorkflow', version: 1.4, config: {{ name: 'Lanzar avisos y calendario', onError: 'continueRegularOutput', alwaysOutputData: true, position: [3080, 160],
  parameters: {{ mode: 'once', source: 'database', workflowId: {{ __rl: true, mode: 'id', value: {J(AVISOS_WF)} }}, workflowInputs: {{ mappingMode: 'defineBelow', value: {{ evento_id: expr('{{{{ $("Registrar en historial").first().json.id }}}}') }}, matchingColumns: [], schema: [ {{ id: 'evento_id', displayName: 'evento_id', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true, type: 'number' }} ], attemptToConvertTypes: false }}, options: {{ waitForSubWorkflow: false }} }} }}, output: [{{}}] }});"""
    aviso_chain = 'lanzarAvisos.to(resGuardado)'

sdk = f"""import {{ workflow, node, trigger, sticky, ifElse, switchCase, expr }} from '@n8n/workflow-sdk';

const entrada = trigger({{ type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2, config: {{ name: 'Entrada', position: [0, 400],
  parameters: {{ inputSource: 'workflowInputs', workflowInputs: {{ values: [ {', '.join(f'{{ name: {J(n)}, type: {J(t)} }}' for n, t in ENTRADAS)} ] }} }} }},
  output: [{{ accion: 'disponibilidad', origen: 'whatsapp' }}] }});
{dt_get('leerConfig', 'Leer configuración', 'res_config', None, '[220, 400]', False)}
{dt_get('leerPersonal', 'Leer personal', 'res_personal', None, '[440, 400]')}
{dt_get('leerCierres', 'Leer cierres', 'res_cierres', [('fin_ts', 'gte', '={{ $now.minus({ days: 8 }).toMillis() }}')], '[660, 400]')}
{dt_get('leerCola', 'Leer cola', 'res_cola', [('creado_ts', 'gte', '={{ $now.minus({ hours: 1 }).toMillis() }}')], '[880, 400]')}
{dt_get('leerReservas', 'Leer reservas', 'res_reservas', [('inicio_ts', 'gte', '={{ $now.minus({ days: 8 }).toMillis() }}')], '[1100, 400]')}
{code('evaluar', 'Evaluar solicitud', code_eval, '[1320, 400]')}
const segunOp = switchCase({{ version: 3.2, config: {{ name: 'Según operación', position: [1540, 400], parameters: {{ rules: {{ values: [ {switch_rules} ] }}, options: {{}} }} }} }});
{setn('devolver', 'Devolver respuesta', [('resultado', 'object', '={{ $json.resultado }}')], '[1760, 120]')}
{dt_write('encolar', 'Encolar bloqueo provisional', 'res_cola', 'insert', columnas('res_cola', ins_cola), '[1760, 320]')}
{dt_get('releerCola', 'Releer cola', 'res_cola', [('creado_ts', 'gte', '={{ $now.minus({ hours: 1 }).toMillis() }}')], '[1980, 320]')}
{dt_get('releerReservas', 'Releer reservas', 'res_reservas', [('inicio_ts', 'gte', '={{ $now.minus({ days: 8 }).toMillis() }}')], '[2200, 320]')}
{code('verificar', 'Verificar conflicto', code_ver, '[2420, 320]')}
const haySitio = ifElse({{ version: 2.2, config: {{ name: '¿Hay sitio asegurado?', position: [2640, 320], parameters: {cond_if('{{ $json.gana }}', 'boolean', 'true')} }} }});
const esNueva = ifElse({{ version: 2.2, config: {{ name: '¿Reserva nueva?', position: [2860, 220], parameters: {cond_if("{{ $('Evaluar solicitud').first().json.tipo }}", 'string', 'equals', 'crear')} }} }});
{dt_write('guardarNueva', 'Guardar reserva nueva', 'res_reservas', 'insert', columnas('res_reservas', ins_fila), '[3080, 120]')}
{dt_write('actualizarMod', 'Actualizar reserva modificada', 'res_reservas', 'update', columnas('res_reservas', upd_mod), '[3080, 320]', id_version, ', alwaysOutputData: true')}
{dt_write('marcarPerdido', 'Marcar bloqueo perdido', 'res_cola', 'update', columnas('res_cola', {'estado': 'perdido'}), '[2860, 480]', condiciones([('id', 'eq', '={{ $json.cola_id }}')]), ", alwaysOutputData: true, onError: 'continueRegularOutput'")}
{setn('resSinSitio', 'Resultado sin sitio', [('resultado', 'object', "={{ $('Verificar conflicto').first().json.resultado }}")], '[3080, 480]')}
{dt_write('cancelarRes', 'Cancelar reserva', 'res_reservas', 'update', columnas('res_reservas', upd_can), '[1760, 560]', id_version, ', alwaysOutputData: true')}
{dt_write('guardarCierre', 'Guardar bloqueo de agenda', 'res_cierres', 'insert', columnas('res_cierres', ins_cierre), '[1760, 720]')}
{dt_write('anularCierre', 'Anular bloqueo de agenda', 'res_cierres', 'update', columnas('res_cierres', {'estado': 'anulado'}), '[1760, 880]', condiciones([('id', 'eq', '={{ $json.cierre_id }}'), ('estado', 'eq', 'activo')]), ', alwaysOutputData: true')}
{code('comprobar', 'Comprobar escritura', code_comp, '[3300, 560]')}
const guardado = ifElse({{ version: 2.2, config: {{ name: '¿Guardado?', position: [3520, 560], parameters: {cond_if('{{ $json.escrito }}', 'boolean', 'true')} }} }});
{dt_write('historial', 'Registrar en historial', 'res_eventos', 'insert', columnas('res_eventos', ins_evento), '[3740, 460]')}
{dt_write('marcarGanado', 'Marcar bloqueo ganado', 'res_cola', 'update', columnas('res_cola', {'estado': 'ganado'}), '[3960, 460]', condiciones([('id', 'eq', "={{ $('Comprobar escritura').first().json.cola_id || -1 }}")]), ", alwaysOutputData: true, onError: 'continueRegularOutput'")}
{aviso_node.replace('[3080, 160]', '[4180, 460]')}
{setn('resGuardado', 'Resultado guardado', [('resultado', 'object', "={{ $('Comprobar escritura').first().json.resultado }}")], '[4400, 460]')}
{dt_write('liberar', 'Liberar bloqueo', 'res_cola', 'update', columnas('res_cola', {'estado': 'perdido'}), '[3740, 660]', condiciones([('id', 'eq', '={{ $json.cola_id || -1 }}')]), ", alwaysOutputData: true, onError: 'continueRegularOutput'")}
{setn('resNoGuardado', 'Resultado no guardado', [('resultado', 'object', "={{ $('Comprobar escritura').first().json.resultado }}")], '[3960, 660]')}

const nota = sticky('## Motor común de reservas\\nÚnico sitio donde se aplican las reglas (horarios, cierres, aforo por zona, bloqueos de agenda) y los permisos. Lo usan el chatbot de WhatsApp, el secretario y el agente telefónico.\\n\\n**Almacenamiento:** Data Tables `res_*` (no Google Sheets).\\n**Choques entre canales:** cada creación/modificación escribe un bloqueo provisional en `res_cola`, relee y solo confirma si cabe contando los bloqueos anteriores. **Cambios concurrentes:** las actualizaciones filtran por id + versión.\\n**Historial:** cada cambio queda en `res_eventos` (antes/después, origen, actor). Los avisos y Google Calendar van aparte y su fallo no afecta a la reserva.\\n⚠️ Tras editar, pulsa **Publish**: los asistentes llaman a la versión publicada.', [entrada, leerConfig, evaluar], {{ color: 4 }});

export default workflow('motor-reservas', 'Reservas · Motor común')
  .add(entrada).to(leerConfig).to(leerPersonal).to(leerCierres).to(leerCola).to(leerReservas).to(evaluar)
  .to(segunOp
    .onCase(0, devolver)
    .onCase(1, encolar.to(releerCola).to(releerReservas).to(verificar).to(haySitio
        .onTrue(esNueva.onTrue(guardarNueva.to(comprobar)).onFalse(actualizarMod.to(comprobar)))
        .onFalse(marcarPerdido.to(resSinSitio))))
    .onCase(2, cancelarRes.to(comprobar))
    .onCase(3, guardarCierre.to(comprobar))
    .onCase(4, anularCierre.to(comprobar)))
  .add(comprobar).to(guardado.onTrue(historial.to(marcarGanado).to({aviso_chain})).onFalse(liberar.to(resNoGuardado)))
  .add(nota);
"""
open(sys.argv[2] if len(sys.argv) > 2 else '/dev/stdout', 'w').write(sdk)
