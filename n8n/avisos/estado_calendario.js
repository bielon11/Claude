// Anota en el historial si la copia en Google Calendar se hizo. No afecta a la reserva.
const j = $input.first().json || {};
const p = $('Preparar aviso y calendario').first().json;
const fallo = j.error || (p.cal.accion !== 'borrar' && !j.id);
return [{ json: { evento_id: p.evento_id, calendario_estado: fallo ? 'error: ' + String(j.error?.message || j.error || 'sin id de evento').slice(0, 150) : 'ok' } }];
