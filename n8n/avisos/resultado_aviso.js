// Resume el envío a cada destinatario. Un fallo de WhatsApp solo se anota: la reserva ya está guardada y no se toca.
const res = $input.all().map(i => i.json);
const enviados = res.filter(j => Array.isArray(j.messages) && j.messages.length).length;
const errores = res.filter(j => !(Array.isArray(j.messages) && j.messages.length)).map(j => String(j.error?.message || j.error || 'error').slice(0, 200));
const fueraVentana = errores.some(e => /131047|24 ?h|re-engagement/i.test(e));
return [{ json: {
  evento_id: $('Preparar aviso y calendario').first().json.evento_id,
  aviso_estado: enviados && !errores.length ? 'enviado' : enviados ? 'parcial' : 'fallido',
  aviso_detalle: `${enviados}/${res.length} enviados` + (errores.length ? '. ' + (fueraVentana ? 'Fuera de la ventana de 24 h de WhatsApp: hace falta una plantilla aprobada. ' : '') + errores.join(' | ') : '')
} }];
