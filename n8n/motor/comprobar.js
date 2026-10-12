// Confirma que la escritura en la Data Table ha devuelto la fila. Las actualizaciones filtran por id + versión:
// si otra petición cambió la reserva entre medias, no se actualiza nada y NO se confirma la operación.
const P = $('Evaluar solicitud').first().json;
const fila = $input.first()?.json || {};
const escrito = fila.id !== undefined && fila.id !== null && fila.id !== '';
let colaId = 0;
try { colaId = Number($('Verificar conflicto').first().json.cola_id) || 0; } catch (e) { colaId = 0; }
if (!escrito) {
  const conflicto = P.op === 'cancelar' || P.tipo === 'modificar' || P.op === 'desbloquear';
  return [{ json: { escrito: false, cola_id: colaId, resultado: conflicto
    ? { ok: false, motivo: 'modificada_por_otro', detalle: 'El registro ha cambiado mientras se procesaba. No se ha aplicado nada; vuelve a consultarlo.' }
    : { ok: false, motivo: 'error_guardado', detalle: 'No se ha podido guardar. No se ha confirmado nada.' } } }];
}
return [{ json: { escrito: true, cola_id: colaId, evento: P.evento, resultado: P.resultado_exito } }];
