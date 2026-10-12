
// Comprobación final tras escribir el bloqueo provisional en res_cola. Se releen la cola y DESPUÉS las reservas
// (en este orden, para que una reserva que se confirme entre ambas lecturas cuente al menos una vez).
// Cuentan: reservas confirmadas + bloqueos pendientes vivos que entraron ANTES que el nuestro (id menor) + bloqueos de agenda.
const P = $('Evaluar solicitud').first().json;
const mioId = Number($('Encolar bloqueo provisional').first().json.id);
const cola2 = filas('Releer cola');
const reservas2 = filas('Releer reservas');
const cierres2 = filas('Leer cierres');
const mio = cola2.find(c => Number(c.id) === mioId);
const ctx2 = crearContexto(reservas2, cola2, cierres2);
const motivos = [];
let resultado = null;
if (!mio) motivos.push('No se ha podido leer el bloqueo provisional recién escrito.');
const original = P.tipo === 'modificar' ? reservas2.find(r => Number(r.id) === Number(P.reserva_id)) : null;
if (P.tipo === 'modificar' && (!original || norm(original.estado) !== ACTIVA || Number(original.version) !== Number(P.version_actual))) {
  motivos.push('modificada_por_otro');
  resultado = { ok: false, motivo: 'modificada_por_otro', detalle: 'La reserva ha cambiado o se ha cancelado mientras se procesaba. No se ha aplicado el cambio; vuelve a consultarla.' };
}
if (P.tipo === 'crear') {
  const yaGuardada = ctx2.activas.find(r => norm(r.clave_idem) === norm(P.cola.clave_idem));
  if (yaGuardada) {
    motivos.push('duplicado');
    resultado = Number(yaGuardada.personas) === Number(P.fila.personas)
      ? { ok: true, accion: 'reserva_creada', idempotente: true, detalle: 'Esta reserva ya estaba guardada (no se ha duplicado).', reserva: vista(yaGuardada, P.es_personal) }
      : { ok: false, motivo: 'ya_reservado', detalle: 'Ya existe una reserva confirmada con ese teléfono/nombre a esa hora.', reserva: vista(yaGuardada, P.es_personal) };
  } else if (cola2.some(c => Number(c.id) < mioId && norm(c.estado) === 'pendiente' && norm(c.clave_idem) === norm(P.cola.clave_idem) && nowMs - Number(c.creado_ts) < CADUCIDAD * 60000)) {
    motivos.push('duplicado_en_curso');
    resultado = { ok: false, motivo: 'duplicado_en_curso', detalle: 'Esta misma reserva se está guardando ahora mismo desde otra petición. No se ha creado otra; consulta las reservas en unos segundos.' };
  }
}
if (mio && !motivos.length) {
  const op = { colaAntesDe: mioId, excluirColaId: mioId, excluirReservaId: P.tipo === 'modificar' ? P.reserva_id : undefined };
  const ocup = ctx2.ocupadas(normZona(mio.zona), Number(mio.inicio_ts), Number(mio.fin_ts), op);
  if (ocup + Number(mio.personas) > CAPACIDAD[normZona(mio.zona)]) {
    motivos.push(`Capacidad superada en ${mio.zona}: ${ocup} + ${mio.personas} > ${CAPACIDAD[normZona(mio.zona)]}`);
    const opAlt = { excluirColaId: mioId, excluirReservaId: op.excluirReservaId };
    const s = dt(mio.inicio_ts);
    resultado = {
      ok: false, motivo: 'ocupado_simultaneamente',
      detalle: 'Otra persona acaba de ocupar ese hueco en este mismo momento. No se ha confirmado nada' + (P.tipo === 'modificar' ? ' y la reserva original se mantiene sin cambios.' : '.'),
      zonas_con_sitio_a_esa_hora: ctx2.zonasConSitio(Number(mio.inicio_ts), Number(mio.fin_ts), Number(mio.personas), '', opAlt),
      alternativas: alternativas(ctx2, s.toFormat('yyyy-MM-dd'), s.toFormat('HH:mm'), Number(mio.personas), '', P.es_personal, opAlt)
    };
  }
}
const gana = motivos.length === 0;
if (!resultado && !gana) resultado = { ok: false, motivo: 'error_interno', detalle: motivos.join('; ') };
return [{ json: { gana, motivos, resultado, cola_id: mioId } }];
