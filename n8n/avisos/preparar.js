// Prepara, a partir de un evento del historial (res_eventos), el aviso de WhatsApp al personal y la sincronización con Google Calendar.
// La reserva YA está guardada: si algo de aquí falla, solo se anota en el evento (nunca se repite ni se crea otra reserva).
const TZ = 'Europe/Madrid';
const ev = $('Leer evento').first().json;
const norm = v => String(v ?? '').trim();
const normTel = v => String(v ?? '').replace(/\D/g, '');
const ok = j => j && j.id !== undefined && j.id !== null && j.id !== '';
const cfg = {};
for (const i of $('Leer configuración').all()) { if (ok(i.json) && norm(i.json.clave)) cfg[norm(i.json.clave)] = norm(i.json.valor); }
const personal = $('Leer personal').all().map(i => i.json).filter(ok);
const parse = s => { try { return s ? JSON.parse(s) : null; } catch (e) { return null; } };
const antes = parse(ev.antes);
const despues = parse(ev.despues);
const r = despues || antes || {};
const fmt = x => x && x.inicio_ts ? DateTime.fromMillis(Number(x.inicio_ts), { zone: TZ }).setLocale('es').toFormat("ccc d/LL HH:mm") : '';
const linea = x => x ? `*${norm(x.nombre)}* · ${x.personas} pers · ${norm(x.zona)} · ${fmt(x)}` : '';
const canal = { whatsapp: 'WhatsApp', llamada: 'llamada', secretario: 'secretario' }[norm(ev.origen)] || norm(ev.origen);

let texto = '';
if (ev.tipo === 'creada') texto = `🆕 *Nueva reserva* (${canal})\n${linea(despues)}\n📞 +${normTel(r.telefono) || '-'}${norm(r.observaciones) ? '\n📝 ' + norm(r.observaciones) : ''}\nCódigo ${norm(ev.reserva_codigo)}`;
else if (ev.tipo === 'modificada') texto = `✏️ *Reserva modificada* (${canal})\nAntes: ${linea(antes)}\nAhora: ${linea(despues)}\n📞 +${normTel(r.telefono) || '-'}\nCódigo ${norm(ev.reserva_codigo)}`;
else if (ev.tipo === 'cancelada') texto = `❌ *Reserva cancelada* (${canal})\n${linea(antes)}\n📞 +${normTel(r.telefono) || '-'}\nCódigo ${norm(ev.reserva_codigo)}`;
else if (ev.tipo === 'escalado') texto = `☎️ *Llamada que necesita a una persona*\n📞 +${normTel(r.telefono) || 'número oculto'}\nMotivo: ${norm(r.motivo) || '-'}\n${norm(r.resumen)}`;
else if (ev.tipo === 'error') texto = `⚠️ *Error en la automatización*\n${norm(r.workflow)} · ${norm(r.nodo)}\n${norm(r.mensaje).slice(0, 500)}\n${norm(r.url)}`;
else texto = `ℹ️ ${norm(ev.tipo)} ${norm(ev.reserva_codigo)}`;

const destinatarios = personal.filter(p => (p.activo === true || p.activo === 'true') && (p.recibe_avisos === true || p.recibe_avisos === 'true') && normTel(p.telefono))
  .map(p => ({ telefono: normTel(p.telefono), nombre: norm(p.nombre) }));
const phoneNumberId = norm(cfg.whatsapp_phone_number_id);
const quiereAviso = (ev.avisar === true || ev.avisar === 'true') && norm(ev.aviso_estado) === 'pendiente';
let avisoEstado = '';
let avisoDetalle = '';
if (quiereAviso && !destinatarios.length) { avisoEstado = 'sin_destinatarios'; avisoDetalle = 'Nadie de res_personal tiene recibe_avisos=true'; }
else if (quiereAviso && !phoneNumberId) { avisoEstado = 'fallido'; avisoDetalle = 'Falta whatsapp_phone_number_id en res_config'; }

// Google Calendar: copia visual por zona. Clave privada = código de la reserva.
const calDe = z => { const v = norm(cfg[norm(z) === 'Terraza' ? 'calendario_terraza_id' : 'calendario_interior_id']); return v.includes('@') ? v : ''; };
let cal = { accion: 'nada' };
if (norm(ev.calendario_estado) === 'pendiente') {
  const cuerpo = despues ? {
    summary: `${norm(despues.nombre)} · ${despues.personas} ${Number(despues.personas) === 1 ? 'persona' : 'personas'} · ${norm(despues.zona)}`,
    description: `Teléfono: +${normTel(despues.telefono) || '-'}\nObservaciones: ${norm(despues.observaciones) || '-'}\nOrigen: ${canal}\nCódigo: ${norm(despues.codigo)}`,
    start: { dateTime: DateTime.fromMillis(Number(despues.inicio_ts), { zone: TZ }).toISO(), timeZone: TZ },
    end: { dateTime: DateTime.fromMillis(Number(despues.fin_ts), { zone: TZ }).toISO(), timeZone: TZ },
    extendedProperties: { private: { codigo: norm(despues.codigo) } }
  } : null;
  if (ev.tipo === 'creada') cal = { accion: 'crear', cal_nuevo: calDe(despues.zona), cuerpo };
  else if (ev.tipo === 'modificada') cal = { accion: 'reemplazar', cal_anterior: calDe(antes.zona), cal_nuevo: calDe(despues.zona), cuerpo };
  else if (ev.tipo === 'cancelada') cal = { accion: 'borrar', cal_anterior: calDe(antes.zona) };
  if ((cal.accion !== 'borrar' && !cal.cal_nuevo) || (cal.accion !== 'crear' && !cal.cal_anterior)) cal = { accion: 'no_configurado' };
}
return [{ json: {
  evento_id: ev.id, codigo: norm(ev.reserva_codigo), texto, phone_number_id: phoneNumberId,
  hay_aviso: quiereAviso && !avisoEstado, destinatarios, aviso_estado_previo: avisoEstado, aviso_detalle_previo: avisoDetalle,
  cal
} }];
