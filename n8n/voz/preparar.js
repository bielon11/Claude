// Traduce la llamada de herramienta del agente de voz (ElevenLabs u otro) a una petición del Motor común.
// Seguridad: el teléfono del cliente para ver/modificar/cancelar es SIEMPRE el número que llama (caller ID),
// nunca uno dictado; si el número está oculto, esas acciones no se permiten y el agente debe transferir.
const b = $('Llamada del agente de voz').first().json.body || {};
const a = b.args && typeof b.args === 'object' ? { ...b, ...b.args } : b;
const herramienta = String(a.herramienta || a.tool || '').trim();
const soloDigitos = v => String(v ?? '').replace(/\D/g, '');
const normalizarTel = v => { let t = soloDigitos(v); if (t.startsWith('00')) t = t.slice(2); if (t.length === 9 && /^[6789]/.test(t)) t = '34' + t; return t.length >= 9 ? t : ''; };
const callerId = normalizarTel(a.caller_id);
const map = { consultar_disponibilidad: 'disponibilidad', crear_reserva: 'crear', ver_mis_reservas: 'reservas_cliente', modificar_reserva: 'modificar', cancelar_reserva: 'cancelar' };
const accion = map[herramienta] || '';
const tz = 'Europe/Madrid';
const hoy = DateTime.now().setZone(tz).setLocale('es');
const calendario = Array.from({ length: 8 }, (_, i) => { const d = hoy.plus({ days: i }); return { dia: i === 0 ? 'hoy' : i === 1 ? 'mañana' : d.toFormat('cccc'), fecha: d.toFormat('yyyy-MM-dd'), texto: d.toFormat("cccc d 'de' LLLL") }; });
const telefono = accion === 'crear' ? (callerId || normalizarTel(a.telefono_contacto)) : callerId;
return [{ json: {
  herramienta, accion, call_id: String(a.call_id || a.conversation_id || ''), caller_id: callerId,
  ahora: hoy.toFormat("cccc d 'de' LLLL yyyy, HH:mm"), calendario,
  motor: {
    accion, origen: 'llamada', telefono_cliente: telefono, nombre: String(a.nombre || ''), fecha: String(a.fecha || ''), hora: String(a.hora || ''),
    personas: Number(a.personas) || 0, zona: String(a.zona || ''), observaciones: String(a.observaciones || ''), reserva_ref: String(a.reserva_actual || '')
  },
  escalado: { motivo: String(a.motivo || ''), resumen: String(a.resumen || ''), telefono: callerId }
} }];
