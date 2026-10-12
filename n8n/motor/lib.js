// ===== Librería común del motor de reservas v3 (Data Tables). Misma copia en "Evaluar solicitud" y "Verificar conflicto" =====
const TZ = 'Europe/Madrid';
const ZONAS = ['Interior', 'Terraza'];
const ACTIVA = 'confirmada';
const DIAS = ['', 'lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo'];
const norm = v => String(v ?? '').trim();
const normTel = v => String(v ?? '').replace(/\D/g, '');
const plano = v => norm(v).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const esVerdadero = v => v === true || v === 'true' || v === 1 || v === '1';
// Filas reales de un nodo Data table (los nodos tienen "Always output data", así que se descarta el item vacío).
const filas = nodo => { try { return $(nodo).all().map(i => i.json).filter(j => j && j.id !== undefined && j.id !== null && j.id !== ''); } catch (e) { return []; } };

const ahora = DateTime.now().setZone(TZ);
const nowMs = ahora.toMillis();
const hoyISO = ahora.toFormat('yyyy-MM-dd');

const cfg = {};
for (const r of filas('Leer configuración')) { if (norm(r.clave)) cfg[norm(r.clave)] = norm(r.valor); }
const faltan = [];
const cfgNum = (k, def) => {
  const raw = cfg[k];
  if (raw === undefined || raw === '' || isNaN(Number(raw))) { if (def === undefined) faltan.push(k); return def ?? 0; }
  return Number(raw);
};
const DURACION = cfgNum('duracion_reserva_min');
const CAPACIDAD = { Interior: cfgNum('capacidad_interior'), Terraza: cfgNum('capacidad_terraza') };
const MAX_CLIENTE = Math.min(cfgNum('max_personas_reserva', 99), Math.max(CAPACIDAD.Interior, CAPACIDAD.Terraza));
const MAX_PERSONAL = Math.max(CAPACIDAD.Interior, CAPACIDAD.Terraza);
const MARGEN = cfgNum('margen_entre_reservas_min', 0);
const ANTELACION = cfgNum('antelacion_minima_min', 0);
const PASO = cfgNum('paso_alternativas_min', 30) || 30;
const CADUCIDAD = cfgNum('caducidad_bloqueo_min', 5);
const AVISO_GRUPO = cfgNum('aviso_grupo_desde', 8);
const INICIO_CENA = /^\d{2}:\d{2}$/.test(norm(cfg.hora_inicio_cena)) ? norm(cfg.hora_inicio_cena) : '18:00';
for (let d = 1; d <= 7; d++) { if (!cfg['horario_' + DIAS[d]]) faltan.push('horario_' + DIAS[d]); }

const normZona = z => { const v = plano(z); if (v.startsWith('int')) return 'Interior'; if (v.startsWith('ter')) return 'Terraza'; if (v.startsWith('tod') || v === 'ambas') return 'Todas'; return ''; };
const dt = ms => DateTime.fromMillis(Number(ms), { zone: TZ });
const solapa = (s1, e1, s2, e2, margen) => s1 < e2 + margen * 60000 && s2 < e1 + margen * 60000;

// "hoy", "mañana", "pasado mañana", YYYY-MM-DD o DD/MM/YYYY -> YYYY-MM-DD en la zona horaria del negocio.
function resolverFecha(v) {
  const t = plano(v);
  if (!t || t === 'hoy') return hoyISO;
  if (t === 'manana') return ahora.plus({ days: 1 }).toFormat('yyyy-MM-dd');
  if (t === 'pasado manana') return ahora.plus({ days: 2 }).toFormat('yyyy-MM-dd');
  if (/^\d{4}-\d{2}-\d{2}$/.test(t)) return DateTime.fromFormat(t, 'yyyy-MM-dd', { zone: TZ }).isValid ? t : '';
  const m = t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (m) { const d = DateTime.fromObject({ year: +m[3], month: +m[2], day: +m[1] }, { zone: TZ }); return d.isValid ? d.toFormat('yyyy-MM-dd') : ''; }
  return '';
}
const normHora = v => { const m = norm(v).match(/^(\d{1,2})[:.h]?(\d{2})?$/); if (!m) return ''; const h = +m[1], mi = +(m[2] || 0); return h < 24 && mi < 60 ? String(h).padStart(2, '0') + ':' + String(mi).padStart(2, '0') : ''; };

function franjasDe(fecha) {
  const d = DateTime.fromFormat(fecha, 'yyyy-MM-dd', { zone: TZ });
  const v = norm(cfg['horario_' + DIAS[d.weekday]]);
  if (!v || v.toUpperCase() === 'CERRADO') return [];
  return v.split(',').map(t => t.trim()).filter(Boolean).map(t => { const [a, b] = t.split('-').map(x => x.trim()); return { desde: a, hasta: b || a }; });
}
function cerradoPorCierre(fecha) {
  return norm(cfg.cierres).split(',').map(x => x.trim()).filter(Boolean).some(c => { const [a, b] = c.split('/').map(x => x.trim()); return b ? fecha >= a && fecha <= b : fecha === a; });
}

// Reglas de negocio de una solicitud (las mismas para los 3 canales; el personal no tiene antelación mínima
// y puede superar el máximo de personas por reserva automática, pero nunca el aforo de la zona).
function validar(fecha, hora, personas, esPersonal) {
  fecha = norm(fecha); hora = norm(hora);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(fecha) || !/^\d{2}:\d{2}$/.test(hora)) return { ok: false, motivo: 'formato_invalido', detalle: 'La fecha debe ser YYYY-MM-DD y la hora HH:MM (24h).' };
  const s = DateTime.fromFormat(fecha + ' ' + hora, 'yyyy-MM-dd HH:mm', { zone: TZ });
  if (!s.isValid || s.toFormat('HH:mm') !== hora) return { ok: false, motivo: 'hora_inexistente', detalle: 'Esa fecha u hora no existe (por ejemplo, por el cambio de hora).' };
  const p = Number(personas);
  const max = esPersonal ? MAX_PERSONAL : MAX_CLIENTE;
  if (!Number.isInteger(p) || p < 1) return { ok: false, motivo: 'personas_invalidas', detalle: 'Indica un número de personas válido.' };
  if (p > max) return { ok: false, motivo: 'grupo_grande', detalle: esPersonal ? `El aforo máximo de una zona es ${max} personas.` : `Como máximo se pueden reservar ${max} personas. Para grupos mayores hay que llamar al restaurante.` };
  const minimo = esPersonal ? nowMs - 30 * 60000 : nowMs + ANTELACION * 60000;
  if (s.toMillis() < minimo) return { ok: false, motivo: esPersonal ? 'en_el_pasado' : 'antelacion_insuficiente', detalle: esPersonal ? 'Esa hora ya ha pasado.' : `Las reservas se hacen con al menos ${ANTELACION} minutos de antelación y no pueden ser en el pasado.` };
  if (cerradoPorCierre(fecha)) return { ok: false, motivo: 'cerrado', detalle: 'El restaurante está cerrado ese día.' };
  const fr = franjasDe(fecha);
  if (!fr.length) return { ok: false, motivo: 'dia_cerrado', detalle: 'El restaurante no abre ese día de la semana.' };
  if (!fr.some(f => hora >= f.desde && hora <= f.hasta)) return { ok: false, motivo: 'fuera_de_horario', detalle: 'Horas de inicio admitidas ese día: ' + fr.map(f => f.desde + '-' + f.hasta).join(', ') };
  const ini = s.toMillis();
  return { ok: true, ini, fin: ini + DURACION * 60000, personas: p, fecha, hora };
}

// Contexto de ocupación: reservas confirmadas + bloqueos provisionales vivos de la cola + cierres/bloqueos de agenda.
function crearContexto(reservas, cola, cierres) {
  const activas = reservas.filter(r => norm(r.estado) === ACTIVA);
  const colaVivaYSinGuardar = c => {
    if (norm(c.estado) !== 'pendiente' || nowMs - Number(c.creado_ts || 0) >= CADUCIDAD * 60000) return false;
    // Si la reserva de ese bloqueo ya está guardada, no se cuenta dos veces.
    return !activas.some(r => norm(r.codigo) === norm(c.codigo) && Number(r.inicio_ts) === Number(c.inicio_ts) && normZona(r.zona) === normZona(c.zona) && Number(r.personas) === Number(c.personas));
  };
  function ocupadas(zona, ini, fin, op) {
    op = op || {};
    let total = 0;
    for (const r of activas) {
      if (normZona(r.zona) !== zona || (op.excluirReservaId && Number(r.id) === Number(op.excluirReservaId))) continue;
      if (solapa(ini, fin, Number(r.inicio_ts), Number(r.fin_ts), MARGEN)) total += Number(r.personas) || 0;
    }
    for (const c of cola) {
      if (normZona(c.zona) !== zona || !colaVivaYSinGuardar(c)) continue;
      if (op.excluirColaId && Number(c.id) === Number(op.excluirColaId)) continue;
      if (op.colaAntesDe && Number(c.id) >= Number(op.colaAntesDe)) continue;
      if (op.excluirReservaId && Number(c.reserva_id) === Number(op.excluirReservaId)) continue;
      if (solapa(ini, fin, Number(c.inicio_ts), Number(c.fin_ts), MARGEN)) total += Number(c.personas) || 0;
    }
    for (const b of cierres) {
      const z = normZona(b.zona);
      if (norm(b.estado) !== 'activo' || (z !== zona && z !== 'Todas')) continue;
      if (solapa(ini, fin, Number(b.inicio_ts), Number(b.fin_ts), 0)) total += Number(b.plazas) > 0 ? Number(b.plazas) : CAPACIDAD[zona];
    }
    return total;
  }
  const libres = (zona, ini, fin, op) => Math.max(CAPACIDAD[zona] - ocupadas(zona, ini, fin, op), 0);
  const zonasConSitio = (ini, fin, personas, zona, op) => ZONAS
    .filter(z => (!zona || zona === 'Todas' || z === zona) && CAPACIDAD[z] > 0 && libres(z, ini, fin, op) >= personas)
    .sort((a, b) => libres(b, ini, fin, op) - libres(a, ini, fin, op));
  return { activas, ocupadas, libres, zonasConSitio };
}

function alternativas(ctx, fecha, hora, personas, zona, esPersonal, op) {
  const res = []; const vistos = new Set();
  const probar = (f, h, z) => {
    const key = f + ' ' + h + ' ' + z; if (vistos.has(key)) return false; vistos.add(key);
    const v = validar(f, h, personas, esPersonal); if (!v.ok) return false;
    const zonas = ctx.zonasConSitio(v.ini, v.fin, v.personas, z, op); if (!zonas.length) return false;
    res.push({ fecha: f, hora: h, zonas }); return true;
  };
  if (zona && zona !== 'Todas') probar(fecha, hora, zona === 'Interior' ? 'Terraza' : 'Interior');
  const objetivo = /^\d{2}:\d{2}$/.test(norm(hora)) ? norm(hora) : '21:00';
  const minutos = h => Number(h.slice(0, 2)) * 60 + Number(h.slice(3, 5));
  const horasDelDia = f => { const l = []; for (const fr of franjasDe(f)) for (let m = minutos(fr.desde); m <= minutos(fr.hasta); m += PASO) l.push(String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0')); return l.sort((a, b) => Math.abs(minutos(a) - minutos(objetivo)) - Math.abs(minutos(b) - minutos(objetivo))); };
  if (/^\d{4}-\d{2}-\d{2}$/.test(norm(fecha))) {
    for (const h of horasDelDia(fecha)) { if (res.length >= 4) break; probar(fecha, h, zona); }
    const d = DateTime.fromFormat(fecha, 'yyyy-MM-dd', { zone: TZ });
    for (let i = 1; i <= 14 && res.length < 5; i++) { const f = d.plus({ days: i }).toFormat('yyyy-MM-dd'); for (const h of horasDelDia(f)) { if (probar(f, h, zona)) break; } }
  }
  return res.slice(0, 5);
}

const ALFABETO = 'ACDEFHJKMNPRTUVWXY3479';
const nuevoCodigo = (prefijo, usados) => { for (;;) { let c = prefijo; for (let i = 0; i < 5; i++) c += ALFABETO[Math.floor(Math.random() * ALFABETO.length)]; if (!usados.has(c)) return c; } };
const claveIdem = (tel, nombre, ini) => (normTel(tel) ? 't' + normTel(tel) : 'n' + plano(nombre).replace(/[^a-z0-9]/g, '')) + '-' + dt(ini).toFormat('yyyyMMddHHmm');
const franjaDe = hora => (hora >= INICIO_CENA ? 'cena' : 'comida');
// Vista de una reserva para devolver a los asistentes. Los canales de clientes no reciben código ni datos internos.
const vista = (r, conInternos) => {
  const v = { fecha: norm(r.fecha), dia: dt(r.inicio_ts).setLocale('es').toFormat('cccc d LLLL'), hora: norm(r.hora), nombre: norm(r.nombre), personas: Number(r.personas) || 0, zona: norm(r.zona), observaciones: norm(r.observaciones), estado: norm(r.estado) };
  if (conInternos) Object.assign(v, { codigo: norm(r.codigo), telefono: normTel(r.telefono), origen: norm(r.origen), franja: franjaDe(norm(r.hora)) });
  return v;
};
// ===== Fin librería =====
