const fs = require('fs');
const { DateTime } = require('luxon');
const dir = require('path').join(__dirname, '..', 'motor') + '/';
const lib = fs.readFileSync(dir + 'lib.js', 'utf8');
const srcEvaluar = fs.readFileSync(dir + 'evaluar.js', 'utf8');
const srcVerificar = fs.readFileSync(dir + 'verificar.js', 'utf8');
const mk = body => new Function('$', 'DateTime', lib + '\n' + body);
const fEval = mk(srcEvaluar), fVer = mk(srcVerificar);

const cfgRows = [
  ['horario_lunes', 'CERRADO'], ['horario_martes', '13:00-15:30,20:00-22:30'], ['horario_miercoles', '13:00-15:30,20:00-22:30'], ['horario_jueves', '13:00-15:30,20:00-22:30'],
  ['horario_viernes', '13:00-15:30,20:00-22:30'], ['horario_sabado', '13:00-15:30,20:00-22:30'], ['horario_domingo', '13:00-15:30,20:00-22:30'], ['cierres', '2027-01-07/2027-01-21'],
  ['duracion_reserva_min', '120'], ['margen_entre_reservas_min', '15'], ['max_personas_reserva', '10'], ['antelacion_minima_min', '60'], ['paso_alternativas_min', '30'],
  ['caducidad_bloqueo_min', '5'], ['capacidad_interior', '5'], ['capacidad_terraza', '5'], ['aviso_grupo_desde', '8'], ['hora_inicio_cena', '18:00']
].map(([clave, valor], i) => ({ id: i + 1, clave, valor }));
const personal = [
  { id: 1, telefono: '34600000901', nombre: 'Dueño', rol: 'admin', activo: true },
  { id: 2, telefono: '34600000902', nombre: 'Enc', rol: 'gestion', activo: true },
  { id: 3, telefono: '34600000903', nombre: 'Cam', rol: 'lectura', activo: true },
  { id: 4, telefono: '34600000904', nombre: 'Ex', rol: 'gestion', activo: false }
];
const db = { reservas: [], cola: [], cierres: [], seq: 100 };
const items = arr => arr.length ? arr.map(json => ({ json })) : [{ json: {} }];
function run(fn, nodes) { const $ = n => { if (!(n in nodes)) throw new Error('nodo ' + n); const v = nodes[n]; return { all: () => v, first: () => v[0] }; }; return fn($, DateTime); }
function snapshot() { return { 'Leer configuración': items(cfgRows), 'Leer personal': items(personal), 'Leer reservas': items(db.reservas.map(x => ({ ...x }))), 'Leer cola': items(db.cola.map(x => ({ ...x }))), 'Leer cierres': items(db.cierres.map(x => ({ ...x }))) }; }
function evaluar(entrada, snap) { return run(fEval, { ...(snap || snapshot()), Entrada: [{ json: entrada }] })[0].json; }
// Simula el resto del motor (cola -> relectura -> verificación -> escritura) como hace el workflow.
function encolar(plan) { const row = { id: ++db.seq, ...plan.cola }; db.cola.push(row); return row; }
function verificarYEscribir(entrada, plan, snap, colaRow) {
  const v = run(fVer, { ...snap, Entrada: [{ json: entrada }], 'Evaluar solicitud': [{ json: plan }], 'Encolar bloqueo provisional': [{ json: colaRow }], 'Releer cola': items(db.cola.map(x => ({ ...x }))), 'Releer reservas': items(db.reservas.map(x => ({ ...x }))) })[0].json;
  const c = db.cola.find(x => x.id === colaRow.id);
  if (!v.gana) { c.estado = 'perdido'; return v.resultado; }
  if (plan.tipo === 'crear') db.reservas.push({ id: ++db.seq, ...plan.fila });
  else { const r = db.reservas.find(x => x.id === plan.reserva_id && x.version === plan.version_actual); if (!r) { c.estado = 'perdido'; return { ok: false, motivo: 'modificada_por_otro' }; } Object.assign(r, plan.fila); }
  c.estado = 'ganado';
  return plan.resultado_exito;
}
function motor(entrada) {
  const snap = snapshot();
  const plan = evaluar(entrada, snap);
  if (plan.op === 'respuesta') return plan.resultado;
  if (plan.op === 'cancelar') { const r = db.reservas.find(x => x.id === plan.reserva_id && x.version === plan.version_actual); if (!r) return { ok: false, motivo: 'modificada_por_otro' }; Object.assign(r, plan.fila); return plan.resultado_exito; }
  if (plan.op === 'bloquear') { db.cierres.push({ id: ++db.seq, ...plan.cierre }); return plan.resultado_exito; }
  if (plan.op === 'desbloquear') { db.cierres.find(x => x.id === plan.cierre_id).estado = 'anulado'; return plan.resultado_exito; }
  const colaRow = encolar(plan);
  return verificarYEscribir(entrada, plan, snap, colaRow);
}
module.exports = { motor, evaluar, encolar, verificarYEscribir, snapshot, db };

if (require.main === module) {
  let fallos = 0;
  const check = (nombre, cond, extra) => { console.log((cond ? 'OK   ' : 'FALLO') + ' ' + nombre + (cond ? '' : ' -> ' + JSON.stringify(extra))); if (!cond) fallos++; };
  const tz = 'Europe/Madrid';
  let d = DateTime.now().setZone(tz).plus({ days: 1 });
  while (d.weekday === 1) d = d.plus({ days: 1 });
  const F = d.toFormat('yyyy-MM-dd');
  const W = (o) => ({ origen: 'whatsapp', telefono_cliente: '34611111111', ...o });
  const S = (tel, o) => ({ origen: 'secretario', actor_telefono: tel, ...o });

  let r = motor(W({ accion: 'disponibilidad', fecha: F, hora: '21:00', personas: 4 }));
  check('disponibilidad con sitio', r.ok && r.disponible, r);
  r = motor(W({ accion: 'crear', nombre: 'Marta', fecha: F, hora: '21:00', personas: 4, zona: 'Terraza' }));
  check('crear WhatsApp', r.ok && r.accion === 'reserva_creada' && r.reserva.zona === 'Terraza' && !r.reserva.codigo, r);
  r = motor(W({ accion: 'crear', nombre: 'Marta', fecha: F, hora: '21:00', personas: 4, zona: 'Terraza' }));
  check('reintento crear no duplica', r.ok && r.idempotente === true && db.reservas.length === 1, r);
  r = motor(W({ accion: 'crear', telefono_cliente: '34622222222', nombre: 'Luis', fecha: F, hora: '21:30', personas: 2, zona: 'Terraza' }));
  check('sin sitio en terraza (4+2>5) devuelve alternativas', !r.ok && r.motivo === 'sin_disponibilidad' && r.alternativas.length > 0, r);
  r = motor({ accion: 'crear', origen: 'llamada', telefono_cliente: '34633333333', nombre: 'Ana', fecha: F, hora: '21:30', personas: 2 });
  check('llamada asigna Interior', r.ok && r.reserva.zona === 'Interior', r);
  r = motor(W({ accion: 'crear', nombre: 'X', fecha: F, hora: '23:30', personas: 2 }));
  check('fuera de horario', !r.ok && r.motivo === 'fuera_de_horario', r);
  r = motor(W({ accion: 'crear', nombre: 'X', fecha: F, hora: '21:00', personas: 12 }));
  check('grupo grande cliente', !r.ok && r.motivo === 'grupo_grande', r);

  // Concurrencia: dos canales piden el último hueco a la vez (ambos evalúan con la misma foto antes de escribir).
  const snap = snapshot();
  const eA = W({ accion: 'crear', telefono_cliente: '34644444444', nombre: 'WA', fecha: F, hora: '14:00', personas: 4 , zona: 'Interior'});
  const eB = { accion: 'crear', origen: 'llamada', telefono_cliente: '34655555555', nombre: 'Tel', fecha: F, hora: '14:00', personas: 3, zona: 'Interior' };
  const pA = evaluar(eA, snap), pB = evaluar(eB, snap);
  check('ambos ven sitio antes de escribir', pA.op === 'reservar' && pB.op === 'reservar', [pA, pB]);
  const cA = encolar(pA), cB = encolar(pB);
  const rB = verificarYEscribir(eB, pB, snap, cB);
  const rA = verificarYEscribir(eA, pA, snap, cA);
  check('simultáneas: solo una confirmada', (rA.ok ? 1 : 0) + (rB.ok ? 1 : 0) === 1 && rA.ok && rB.motivo === 'ocupado_simultaneamente', { rA, rB });
  const ocup = db.reservas.filter(x => x.fecha === F && x.hora === '14:00' && x.zona === 'Interior' && x.estado === 'confirmada').reduce((s, x) => s + x.personas, 0);
  check('aforo interior 14:00 no superado', ocup <= 5, ocup);
  // Webhook duplicado concurrente del mismo mensaje
  const snap2 = snapshot();
  const eD = W({ accion: 'crear', telefono_cliente: '34666666666', nombre: 'Dup', fecha: F, hora: '13:00', personas: 2, zona: 'Terraza' });
  const p1 = evaluar(eD, snap2), p2 = evaluar(eD, snap2);
  const c1 = encolar(p1), c2 = encolar(p2);
  const r1 = verificarYEscribir(eD, p1, snap2, c1), r2 = verificarYEscribir(eD, p2, snap2, c2);
  check('duplicado concurrente: 1 reserva', db.reservas.filter(x => x.nombre === 'Dup').length === 1 && r1.ok && (r2.motivo === 'duplicado_en_curso' || r2.idempotente === true), { r1, r2 });

  // Cliente: ver, modificar, cancelar solo lo suyo
  r = motor(W({ accion: 'reservas_cliente' }));
  check('ver reservas propias', r.ok && r.total === 1 && r.reservas[0].nombre === 'Marta', r);
  r = motor(W({ accion: 'modificar', zona: 'Interior', personas: 0 }));
  check('modificar sin sitio mantiene original', !r.ok && r.motivo === 'sin_disponibilidad', r);
  r = motor(W({ accion: 'modificar', hora: '20:00', personas: 3 }));
  check('modificar hora/personas', r.ok && r.reserva.hora === '20:00' && r.reserva.personas === 3, r);
  r = motor({ accion: 'cancelar', origen: 'whatsapp', telefono_cliente: '34699999999' });
  check('otro teléfono no puede cancelar', !r.ok && r.motivo === 'sin_reservas', r);

  // Secretario: permisos
  r = motor(S('34600000999', { accion: 'listar' }));
  check('no autorizado', !r.ok && r.motivo === 'no_autorizado', r);
  r = motor(S('34600000904', { accion: 'listar' }));
  check('personal inactivo bloqueado', !r.ok && r.motivo === 'no_autorizado', r);
  r = motor(S('34600000903', { accion: 'cancelar', reserva_ref: 'x' }));
  check('rol lectura no cancela', !r.ok && r.motivo === 'sin_permiso', r);
  r = motor(S('34600000902', { accion: 'bloquear', fecha: F }));
  check('rol gestion no bloquea', !r.ok && r.motivo === 'sin_permiso', r);
  r = motor({ accion: 'listar', origen: 'whatsapp', telefono_cliente: '34611111111' });
  check('cliente no puede listar', !r.ok && r.motivo === 'sin_permiso', r);
  r = motor(S('34600000903', { accion: 'listar', fecha: F, franja: 'cena' }));
  check('listar cena con totales por zona', r.ok && r.totales.reservas === 2 && r.por_zona.Terraza.personas === 3 && r.por_zona.Interior.personas === 2, r);
  r = motor(S('34600000903', { accion: 'listar', fecha: 'mañana' }));
  check('mañana resuelto con zona horaria', r.ok && r.desde === DateTime.now().setZone(tz).plus({ days: 1 }).toFormat('yyyy-MM-dd'), r);
  r = motor(S('34600000902', { accion: 'buscar', texto_busqueda: 'marta' }));
  check('buscar por nombre', r.ok && r.total === 1 && r.reservas[0].codigo, r);
  const cod = r.reservas[0].codigo;
  r = motor(S('34600000902', { accion: 'modificar', reserva_ref: cod.toLowerCase(), zona: 'Terraza' }));
  check('secretario: sin cambios detectado', r.ok && r.accion === 'sin_cambios', r);
  r = motor(S('34600000902', { accion: 'crear', nombre: 'Walk-in', fecha: F, hora: '13:30', personas: 1 }));
  check('secretario crea sin teléfono', r.ok && r.reserva.codigo && r.reserva.origen === 'secretario', r);
  r = motor(S('34600000901', { accion: 'bloquear', fecha: F, hora: '20:00', hora_hasta: '23:59', zona: 'Terraza', motivo: 'Lluvia' }));
  check('admin bloquea terraza noche', r.ok && r.reservas_ya_existentes_afectadas.length === 1, r);
  r = motor(W({ accion: 'disponibilidad', telefono_cliente: '34677777777', fecha: F, hora: '21:00', personas: 1, zona: 'Terraza' }));
  check('bloqueo de agenda quita disponibilidad', r.ok && r.disponible === false, r);
  const bcod = db.cierres[0].codigo;
  r = motor(S('34600000901', { accion: 'desbloquear', reserva_ref: bcod }));
  check('desbloquear', r.ok, r);
  r = motor(S('34600000902', { accion: 'cancelar', reserva_ref: cod }));
  check('secretario cancela por código', r.ok && r.reserva.estado === 'cancelada', r);
  r = motor(W({ accion: 'reservas_cliente' }));
  check('cancelada ya no aparece', r.ok && r.total === 0, r);
  r = motor(S('34600000902', { accion: 'crear', nombre: 'Tarde', fecha: 'hoy', hora: '00:01', personas: 2 }));
  check('secretario no puede reservar en pasado/horario', !r.ok, r);
  console.log(fallos ? `\n${fallos} FALLOS` : '\nTodo OK');
  process.exit(fallos ? 1 : 0);
}
