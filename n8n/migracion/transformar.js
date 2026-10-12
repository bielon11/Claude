// Convierte las reservas FUTURAS y CONFIRMADAS de la hoja antigua (pestaña Reservas) en filas de res_reservas.
// Idempotente: la clave_idem es teléfono + día/hora, así que volver a ejecutar no duplica nada.
const TZ = 'Europe/Madrid';
const norm = v => String(v ?? '').trim();
const normTel = v => String(v ?? '').replace(/\D/g, '');
const normZona = z => { const v = norm(z).toLowerCase(); return v.startsWith('ter') ? 'Terraza' : 'Interior'; };
let duracion = 120;
for (const i of $('Leer configuración').all()) if (i.json && i.json.clave === 'duracion_reserva_min' && Number(i.json.valor)) duracion = Number(i.json.valor);
const vr = ($('Leer hoja antigua').first().json.valueRanges || [])[0] || {};
const vals = vr.values || [];
const cab = (vals[0] || []).map(h => norm(h));
const ahora = DateTime.now().setZone(TZ);
const ALF = 'ACDEFHJKMNPRTUVWXY3479';
const out = [];
for (const fila of vals.slice(1)) {
  const r = {}; cab.forEach((h, j) => { r[h] = fila[j] ?? ''; });
  if (norm(r.estado) !== 'confirmada') continue;
  const s = DateTime.fromFormat(norm(r['dia/hora reserva']), 'dd/MM/yyyy HH:mm', { zone: TZ });
  if (!s.isValid || s < ahora) continue;
  const tel = normTel(r.telefono);
  let codigo = 'R'; for (let k = 0; k < 5; k++) codigo += ALF[Math.floor(Math.random() * ALF.length)];
  out.push({ json: {
    codigo, nombre: norm(r.nombre), telefono: tel, fecha: s.toFormat('yyyy-MM-dd'), hora: s.toFormat('HH:mm'),
    inicio_ts: s.toMillis(), fin_ts: s.plus({ minutes: duracion }).toMillis(), personas: Number(r.personas) || 0, zona: normZona(r.zona),
    estado: 'confirmada', observaciones: norm(r.observaciones), origen: 'whatsapp', creado_por: 'migracion_google_sheets',
    clave_idem: (tel ? 't' + tel : 'n' + norm(r.nombre).toLowerCase().replace(/[^a-z0-9]/g, '')) + '-' + s.toFormat('yyyyMMddHHmm'),
    version: 1, actualizado_ts: ahora.toMillis()
  } });
}
return out;
