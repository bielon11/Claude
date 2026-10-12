"""Helpers para generar código del Workflow SDK de n8n desde Python (evita escapar a mano el JS de los Code nodes)."""
import json

PROJECT = 'BDIz3NPetSuzJwak'
TABLAS = {
    'res_config': 'm2jypfh6J945oHTM',
    'res_personal': 'YBfxwbhMf3WgU56y',
    'res_reservas': 'Ui2o5NQddV1x41KU',
    'res_cola': 'Quvra6qH9KGHP8QB',
    'res_cierres': 'lZsAxHjyHm70yEpQ',
    'res_eventos': 'erAnVYGFp6ntAN85',
    'res_mensajes': 'lxvRFWOCTPCdlZhi',
}
COLUMNAS = {
    'res_reservas': {'codigo': 'string', 'nombre': 'string', 'telefono': 'string', 'fecha': 'string', 'hora': 'string', 'inicio_ts': 'number', 'fin_ts': 'number', 'personas': 'number', 'zona': 'string', 'estado': 'string', 'observaciones': 'string', 'origen': 'string', 'creado_por': 'string', 'clave_idem': 'string', 'version': 'number', 'actualizado_ts': 'number'},
    'res_cola': {'codigo': 'string', 'accion': 'string', 'zona': 'string', 'inicio_ts': 'number', 'fin_ts': 'number', 'personas': 'number', 'estado': 'string', 'creado_ts': 'number', 'clave_idem': 'string', 'reserva_id': 'number'},
    'res_cierres': {'codigo': 'string', 'fecha': 'string', 'desde': 'string', 'hasta': 'string', 'inicio_ts': 'number', 'fin_ts': 'number', 'zona': 'string', 'plazas': 'number', 'motivo': 'string', 'estado': 'string', 'creado_por': 'string', 'creado_ts': 'number'},
    'res_eventos': {'reserva_codigo': 'string', 'tipo': 'string', 'origen': 'string', 'actor': 'string', 'antes': 'string', 'despues': 'string', 'ts': 'number', 'avisar': 'boolean', 'aviso_estado': 'string', 'aviso_detalle': 'string', 'calendario_estado': 'string'},
    'res_mensajes': {'wamid': 'string', 'canal': 'string', 'telefono': 'string', 'recibido_ts': 'number'},
}

def J(v):
    return json.dumps(v, ensure_ascii=False)


def E(s):
    """expr('...') con el texto como literal JSON (expr ya añade el '=' inicial)."""
    s = str(s)
    if s.startswith('='):
        s = s[1:]
    return f"expr({J(s)})"


def tabla(nombre):
    return f"{{ __rl: true, mode: 'id', value: {J(TABLAS[nombre])}, cachedResultName: {J(nombre)} }}"


def columnas(nombre, valores):
    """valores: dict columna -> expresión n8n (string empezando por '={{' o literal)."""
    tipos = COLUMNAS[nombre]
    vals = ', '.join(f"{J(k)}: {E(v) if '{{' in str(v) else J(v)}" for k, v in valores.items())
    schema = ', '.join(
        f"{{ id: {J(k)}, displayName: {J(k)}, required: false, defaultMatch: false, display: true, type: {J(tipos[k])}, canBeUsedToMatch: true }}"
        for k in valores)
    return f"{{ mappingMode: 'defineBelow', value: {{ {vals} }}, matchingColumns: [], schema: [ {schema} ], attemptToConvertTypes: false, convertFieldsToString: false }}"


def condiciones(conds):
    """conds: lista (columna, condicion, valor_expr|None)"""
    out = []
    for k, c, v in conds:
        if v is None:
            out.append(f"{{ keyName: {J(k)}, condition: {J(c)} }}")
        else:
            out.append(f"{{ keyName: {J(k)}, condition: {J(c)}, keyValue: {E(v) if '{{' in str(v) else J(v)} }}")
    return '{ conditions: [ ' + ', '.join(out) + ' ] }'


def set_fields(asignaciones):
    """asignaciones: lista (nombre, tipo, valor)"""
    a = ', '.join(
        f"{{ id: {J('a-' + n)}, name: {J(n)}, type: {J(t)}, value: {E(v) if '{{' in str(v) else J(v)} }}"
        for n, t, v in asignaciones)
    return f"{{ assignments: {{ assignments: [ {a} ] }}, options: {{}} }}"


def cond_if(left, op_type, operation, right=None):
    r = '' if right is None else f", rightValue: {J(right)}"
    single = ", singleValue: true" if right is None else ''
    return (f"{{ conditions: {{ options: {{ caseSensitive: true, leftValue: '', typeValidation: 'loose', version: 2 }}, "
            f"conditions: [ {{ leftValue: {E(left)}, operator: {{ type: {J(op_type)}, operation: {J(operation)}{single} }}{r} }} ], combinator: 'and' }}, options: {{}} }}")


def lib_code(*partes):
    import pathlib
    base = pathlib.Path(__file__).resolve().parent.parent
    return '\n'.join((base / p).read_text() for p in partes)


MOTOR_ID = 'CyBH9RLyq6B4h71T'
ENTRADAS_MOTOR = [('accion', 'string'), ('origen', 'string'), ('actor_telefono', 'string'), ('telefono_cliente', 'string'), ('nombre', 'string'),
                  ('fecha', 'string'), ('hora', 'string'), ('fecha_hasta', 'string'), ('hora_hasta', 'string'), ('personas', 'number'), ('zona', 'string'),
                  ('observaciones', 'string'), ('reserva_ref', 'string'), ('franja', 'string'), ('texto_busqueda', 'string'), ('plazas', 'number'), ('motivo', 'string')]


def llamar_motor(valores, solo_usados=False):
    """workflowInputs para Execute Workflow / Tool Workflow hacia el motor. valores: dict campo -> expr/literal."""
    vals = []
    campos = [(n, t) for n, t in ENTRADAS_MOTOR if not solo_usados or n in valores]
    for n, t in campos:
        v = valores.get(n, 0 if t == 'number' else '')
        vals.append(f"{J(n)}: {E(v) if isinstance(v, str) and '{{' in v else J(v)}")
    schema = ', '.join(f"{{ id: {J(n)}, displayName: {J(n)}, required: false, defaultMatch: false, display: true, canBeUsedToMatch: true, type: {J(t)} }}" for n, t in campos)
    return f"{{ mappingMode: 'defineBelow', value: {{ {', '.join(vals)} }}, matchingColumns: [], schema: [ {schema} ], attemptToConvertTypes: false, convertFieldsToString: false }}"


def motor_rl():
    return f"{{ __rl: true, mode: 'id', value: {J(MOTOR_ID)}, cachedResultName: 'Reservas · Motor común' }}"
