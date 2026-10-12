
const E = $('Entrada').first().json;
const accion = plano(E.accion);
const origen = plano(E.origen);
const esPersonal = origen === 'secretario';
const responder = resultado => [{ json: { op: 'respuesta', resultado } }];

if (faltan.length) return responder({ ok: false, motivo: 'configuracion_incompleta', detalle: 'Faltan datos en res_config: ' + faltan.join(', ') + '. No se puede gestionar la reserva automáticamente.' });
if (!['whatsapp', 'llamada', 'secretario'].includes(origen)) return responder({ ok: false, motivo: 'origen_desconocido', detalle: 'Origen no válido.' });

// ---- Permisos (control real: el teléfono del actor lo pone el canal, no la IA) ----
const PERMISOS_CLIENTE = ['disponibilidad', 'crear', 'reservas_cliente', 'modificar', 'cancelar'];
const LECTURA = ['disponibilidad', 'listar', 'buscar', 'listar_bloqueos'];
const GESTION = LECTURA.concat(['crear', 'modificar', 'cancelar']);
const PERMISOS_ROL = { lectura: LECTURA, gestion: GESTION, admin: GESTION.concat(['bloquear', 'desbloquear']) };
let actor = '';
if (esPersonal) {
  const p = filas('Leer personal').find(x => normTel(x.telefono) && normTel(x.telefono) === normTel(E.actor_telefono) && esVerdadero(x.activo));
  if (!p) return responder({ ok: false, motivo: 'no_autorizado', detalle: 'Este número no está autorizado como personal.' });
  const rol = plano(p.rol);
  if (!(PERMISOS_ROL[rol] || []).includes(accion)) return responder({ ok: false, motivo: 'sin_permiso', detalle: `Tu rol (${rol || 'sin rol'}) no permite la acción "${accion}". Permitidas: ${(PERMISOS_ROL[rol] || []).join(', ')}.` });
  actor = normTel(p.telefono) + ' (' + norm(p.nombre) + ', ' + rol + ')';
} else {
  if (!PERMISOS_CLIENTE.includes(accion)) return responder({ ok: false, motivo: 'sin_permiso', detalle: 'Acción no disponible para clientes.' });
  actor = normTel(E.telefono_cliente);
}
const telCliente = normTel(E.telefono_cliente);
if (!esPersonal && accion !== 'disponibilidad' && !telCliente) return responder({ ok: false, motivo: 'falta_telefono', detalle: 'No se ha podido identificar el teléfono del cliente (número oculto). Para gestionar reservas hace falta un número de contacto.' });

const reservas = filas('Leer reservas');
const cola = filas('Leer cola');
const cierres = filas('Leer cierres');
const ctx = crearContexto(reservas, cola, cierres);
const zonaPedida = normZona(E.zona) === 'Todas' ? '' : normZona(E.zona);
const fechaPedida = resolverFecha(E.fecha);
const horaPedida = normHora(E.hora);
const usados = new Set(reservas.map(r => norm(r.codigo)).concat(cierres.map(c => norm(c.codigo))));
const sinAlternativas = m => ['grupo_grande', 'formato_invalido', 'personas_invalidas', 'en_el_pasado'].includes(m);
const esHoyOMayor = r => Number(r.inicio_ts) >= ahora.startOf('day').toMillis();
const avisarCliente = (fila, tipo) => !esPersonal && (norm(fila.fecha) === hoyISO || Number(fila.personas) >= AVISO_GRUPO || (tipo === 'cancelada' && norm(fila.fecha) === ahora.plus({ days: 1 }).toFormat('yyyy-MM-dd')));
const evento = (codigo, tipo, antes, despues, avisar, conCalendario) => ({
  reserva_codigo: codigo, tipo, origen, actor, antes: antes ? JSON.stringify(antes) : '', despues: despues ? JSON.stringify(despues) : '', ts: nowMs,
  avisar: !!avisar, aviso_estado: avisar ? 'pendiente' : 'no_aplica', aviso_detalle: '', calendario_estado: conCalendario ? 'pendiente' : 'no_aplica'
});
const propiasVigentes = () => ctx.activas.filter(r => normTel(r.telefono) === telCliente && Number(r.inicio_ts) >= nowMs).sort((a, b) => a.inicio_ts - b.inicio_ts);

// ---- Consultas ----
if (accion === 'disponibilidad') {
  if (!fechaPedida || !horaPedida) return responder({ ok: false, motivo: 'formato_invalido', detalle: 'Indica fecha (YYYY-MM-DD, hoy o mañana) y hora (HH:MM).' });
  const v = validar(fechaPedida, horaPedida, E.personas, esPersonal);
  if (!v.ok) return responder({ ok: true, disponible: false, motivo: v.motivo, detalle: v.detalle, alternativas: sinAlternativas(v.motivo) ? [] : alternativas(ctx, fechaPedida, horaPedida, Number(E.personas) || 2, zonaPedida, esPersonal) });
  const zonas = ctx.zonasConSitio(v.ini, v.fin, v.personas, '', {});
  const disponible = zonaPedida ? zonas.includes(zonaPedida) : zonas.length > 0;
  const r = { ok: true, disponible, fecha: v.fecha, hora: v.hora, personas: v.personas, zonas_con_sitio: zonas, alternativas: disponible ? [] : alternativas(ctx, v.fecha, v.hora, v.personas, zonaPedida, esPersonal), nota: 'La disponibilidad no queda reservada hasta crear la reserva.' };
  if (esPersonal) r.plazas_libres = Object.fromEntries(ZONAS.map(z => [z, ctx.libres(z, v.ini, v.fin, {})]));
  return responder(r);
}

if (accion === 'reservas_cliente') {
  const lista = propiasVigentes().map(r => vista(r, false));
  return responder({ ok: true, total: lista.length, reservas: lista });
}

if (accion === 'listar') {
  const desde = fechaPedida;
  const hasta = norm(E.fecha_hasta) ? resolverFecha(E.fecha_hasta) : desde;
  if (!desde || !hasta || hasta < desde) return responder({ ok: false, motivo: 'formato_invalido', detalle: 'Rango de fechas no válido.' });
  const franja = ['comida', 'cena'].includes(plano(E.franja)) ? plano(E.franja) : 'todo';
  const incluirCanceladas = plano(E.texto_busqueda) === 'incluir_canceladas';
  const lista = reservas
    .filter(r => norm(r.fecha) >= desde && norm(r.fecha) <= hasta && (incluirCanceladas || norm(r.estado) === ACTIVA))
    .filter(r => franja === 'todo' || franjaDe(norm(r.hora)) === franja)
    .filter(r => !zonaPedida || normZona(r.zona) === zonaPedida)
    .sort((a, b) => a.inicio_ts - b.inicio_ts);
  const act = lista.filter(r => norm(r.estado) === ACTIVA);
  const suma = arr => ({ reservas: arr.length, personas: arr.reduce((s, r) => s + (Number(r.personas) || 0), 0) });
  const porZona = Object.fromEntries(ZONAS.map(z => [z, suma(act.filter(r => normZona(r.zona) === z))]));
  const porFranja = { comida: suma(act.filter(r => franjaDe(norm(r.hora)) === 'comida')), cena: suma(act.filter(r => franjaDe(norm(r.hora)) === 'cena')) };
  const cierresRango = cierres.filter(c => norm(c.estado) === 'activo' && norm(c.fecha) >= desde && norm(c.fecha) <= hasta).map(c => ({ codigo: c.codigo, fecha: c.fecha, desde: c.desde, hasta: c.hasta, zona: c.zona, plazas: Number(c.plazas) || 'zona completa', motivo: c.motivo }));
  return responder({ ok: true, desde, hasta, franja, zona: zonaPedida || 'todas', totales: suma(act), por_zona: porZona, por_franja: porFranja, capacidad_simultanea: CAPACIDAD, bloqueos_agenda: cierresRango, reservas: lista.slice(0, 80).map(r => vista(r, true)), truncado: lista.length > 80 });
}

if (accion === 'buscar') {
  const q = plano(E.texto_busqueda || E.nombre);
  const qTel = normTel(E.texto_busqueda || E.telefono_cliente);
  if (!q && !qTel) return responder({ ok: false, motivo: 'faltan_datos', detalle: 'Indica un nombre o teléfono a buscar.' });
  const desde = fechaPedida && norm(E.fecha) ? fechaPedida : hoyISO;
  const lista = reservas
    .filter(r => norm(r.fecha) >= desde)
    .filter(r => (qTel.length >= 6 && normTel(r.telefono).endsWith(qTel)) || (q && plano(r.nombre).includes(q)))
    .sort((a, b) => a.inicio_ts - b.inicio_ts).slice(0, 20).map(r => vista(r, true));
  return responder({ ok: true, total: lista.length, reservas: lista });
}

if (accion === 'listar_bloqueos') {
  const desde = fechaPedida;
  const lista = cierres.filter(c => norm(c.estado) === 'activo' && norm(c.fecha) >= desde).sort((a, b) => a.inicio_ts - b.inicio_ts)
    .map(c => ({ codigo: c.codigo, fecha: c.fecha, desde: c.desde, hasta: c.hasta, zona: c.zona, plazas: Number(c.plazas) || 'zona completa', motivo: c.motivo, creado_por: c.creado_por }));
  return responder({ ok: true, total: lista.length, bloqueos: lista, cierres_fijos_config: norm(cfg.cierres) });
}

// ---- Bloqueos de agenda (solo admin) ----
if (accion === 'bloquear') {
  const fecha = fechaPedida;
  const desde = normHora(E.hora) || '00:00';
  const hasta = normHora(E.hora_hasta) || '23:59';
  const zona = normZona(E.zona) || 'Todas';
  const plazas = Math.max(0, Math.floor(Number(E.plazas) || 0));
  if (!fecha || desde >= hasta) return responder({ ok: false, motivo: 'formato_invalido', detalle: 'Indica fecha y un rango horario válido (desde < hasta).' });
  const ini = DateTime.fromFormat(fecha + ' ' + desde, 'yyyy-MM-dd HH:mm', { zone: TZ }).toMillis();
  const fin = DateTime.fromFormat(fecha + ' ' + hasta, 'yyyy-MM-dd HH:mm', { zone: TZ }).toMillis();
  const afectadas = ctx.activas.filter(r => (zona === 'Todas' || normZona(r.zona) === zona) && solapa(ini, fin, Number(r.inicio_ts), Number(r.fin_ts), 0)).map(r => vista(r, true));
  const codigo = nuevoCodigo('B', usados);
  const cierre = { codigo, fecha, desde, hasta, inicio_ts: ini, fin_ts: fin, zona, plazas, motivo: norm(E.motivo) || norm(E.observaciones), estado: 'activo', creado_por: actor, creado_ts: nowMs };
  return [{ json: { op: 'bloquear', cierre, evento: evento(codigo, 'bloqueo_creado', null, cierre, false, false), resultado_exito: { ok: true, accion: 'bloqueo_creado', bloqueo: { codigo, fecha, desde, hasta, zona, plazas: plazas || 'zona completa', motivo: cierre.motivo }, reservas_ya_existentes_afectadas: afectadas, nota: afectadas.length ? 'Las reservas existentes NO se cancelan automáticamente.' : '' } } }];
}
if (accion === 'desbloquear') {
  const ref = norm(E.reserva_ref).toUpperCase();
  const c = cierres.find(x => norm(x.codigo).toUpperCase() === ref && norm(x.estado) === 'activo');
  if (!c) return responder({ ok: false, motivo: 'bloqueo_no_encontrado', detalle: 'No hay un bloqueo activo con ese código.', bloqueos_activos: cierres.filter(x => norm(x.estado) === 'activo').map(x => ({ codigo: x.codigo, fecha: x.fecha, desde: x.desde, hasta: x.hasta, zona: x.zona })) });
  return [{ json: { op: 'desbloquear', cierre_id: c.id, evento: evento(c.codigo, 'bloqueo_anulado', c, { ...c, estado: 'anulado' }, false, false), resultado_exito: { ok: true, accion: 'bloqueo_anulado', bloqueo: { codigo: c.codigo, fecha: c.fecha, desde: c.desde, hasta: c.hasta, zona: c.zona } } } }];
}

// ---- Crear ----
if (accion === 'crear') {
  const nombre = norm(E.nombre);
  if (!nombre) return responder({ ok: false, motivo: 'faltan_datos', detalle: 'Falta el nombre de la reserva.' });
  if (!fechaPedida || !horaPedida) return responder({ ok: false, motivo: 'formato_invalido', detalle: 'Indica fecha (YYYY-MM-DD) y hora (HH:MM).' });
  const v = validar(fechaPedida, horaPedida, E.personas, esPersonal);
  if (!v.ok) return responder({ ok: false, motivo: v.motivo, detalle: v.detalle, alternativas: sinAlternativas(v.motivo) ? [] : alternativas(ctx, fechaPedida, horaPedida, Number(E.personas) || 2, zonaPedida, esPersonal) });
  const clave = claveIdem(telCliente, nombre, v.ini);
  const existente = ctx.activas.find(r => norm(r.clave_idem) === clave);
  if (existente) {
    // Reintento o mensaje duplicado: la reserva ya está guardada, no se crea otra.
    if (Number(existente.personas) === v.personas) return responder({ ok: true, accion: 'reserva_creada', idempotente: true, detalle: 'Esta reserva ya estaba guardada (no se ha duplicado).', reserva: vista(existente, esPersonal) });
    return responder({ ok: false, motivo: 'ya_reservado', detalle: 'Ya existe una reserva confirmada con ese teléfono/nombre a esa misma hora. Usa modificar si quiere cambiarla.', reserva: vista(existente, esPersonal) });
  }
  const zonas = ctx.zonasConSitio(v.ini, v.fin, v.personas, zonaPedida, {});
  if (!zonas.length) return responder({ ok: false, motivo: 'sin_disponibilidad', detalle: 'No hay sitio para esa fecha, hora, número de personas y zona.', alternativas: alternativas(ctx, v.fecha, v.hora, v.personas, zonaPedida, esPersonal) });
  const zona = zonas[0];
  const codigo = nuevoCodigo('R', usados);
  const fila = { codigo, nombre, telefono: telCliente, fecha: v.fecha, hora: v.hora, inicio_ts: v.ini, fin_ts: v.fin, personas: v.personas, zona, estado: ACTIVA, observaciones: norm(E.observaciones), origen, creado_por: actor, clave_idem: clave, version: 1, actualizado_ts: nowMs };
  return [{ json: {
    op: 'reservar', tipo: 'crear', fila, reserva_id: 0, version_actual: 0, es_personal: esPersonal,
    cola: { codigo, accion: 'crear', zona, inicio_ts: v.ini, fin_ts: v.fin, personas: v.personas, estado: 'pendiente', creado_ts: nowMs, clave_idem: clave, reserva_id: 0 },
    evento: evento(codigo, 'creada', null, fila, avisarCliente(fila, 'creada'), true),
    resultado_exito: { ok: true, accion: 'reserva_creada', reserva: vista(fila, esPersonal) }
  } }];
}

// ---- Modificar / cancelar ----
if (accion === 'modificar' || accion === 'cancelar') {
  const ref = norm(E.reserva_ref);
  let candidatas;
  if (esPersonal) {
    candidatas = ctx.activas.filter(esHoyOMayor);
    const porCodigo = candidatas.filter(r => norm(r.codigo).toUpperCase() === ref.toUpperCase());
    if (ref && porCodigo.length) candidatas = porCodigo;
    else {
      const m = ref.match(/(\S+)\s+(\d{1,2}[:.h]\d{2})/);
      const f = m ? resolverFecha(m[1]) : '';
      const h = m ? normHora(m[2]) : '';
      if (f && h) candidatas = candidatas.filter(r => norm(r.fecha) === f && norm(r.hora) === h);
      else if (ref) candidatas = [];
      const q = plano(E.texto_busqueda);
      if (q) candidatas = candidatas.filter(r => plano(r.nombre).includes(q));
    }
  } else {
    candidatas = propiasVigentes();
    if (ref) {
      const m = ref.match(/(\S+)\s+(\d{1,2}[:.h]\d{2})/);
      const f = m ? resolverFecha(m[1]) : '';
      const h = m ? normHora(m[2]) : '';
      candidatas = candidatas.filter(r => norm(r.fecha) === f && norm(r.hora) === h);
    }
  }
  if (candidatas.length !== 1) {
    const sinNada = esPersonal ? !candidatas.length : !propiasVigentes().length;
    return responder({
      ok: false, motivo: sinNada ? 'sin_reservas' : 'reserva_no_identificada',
      detalle: sinNada ? (esPersonal ? 'No encuentro ninguna reserva confirmada con esa referencia.' : 'Este número no tiene reservas futuras confirmadas.') : 'Hay varias reservas posibles: indica cuál (día y hora' + (esPersonal ? ' o código' : '') + ').',
      reservas: (esPersonal ? candidatas : propiasVigentes()).slice(0, 15).map(r => vista(r, esPersonal))
    });
  }
  const r = candidatas[0];
  const antes = { ...r }; delete antes.createdAt; delete antes.updatedAt;
  if (accion === 'cancelar') {
    const despues = { ...antes, estado: 'cancelada', version: Number(r.version) + 1, actualizado_ts: nowMs };
    return [{ json: {
      op: 'cancelar', reserva_id: r.id, version_actual: Number(r.version), fila: { estado: 'cancelada', version: Number(r.version) + 1, actualizado_ts: nowMs },
      evento: evento(r.codigo, 'cancelada', antes, despues, avisarCliente(r, 'cancelada'), true),
      resultado_exito: { ok: true, accion: 'cancelada', reserva: vista(despues, esPersonal) }
    } }];
  }
  const fecha = fechaPedida && norm(E.fecha) ? fechaPedida : norm(r.fecha);
  const hora = horaPedida || norm(r.hora);
  const personas = Number(E.personas) > 0 ? Number(E.personas) : Number(r.personas);
  const v = validar(fecha, hora, personas, esPersonal);
  const op = { excluirReservaId: r.id };
  if (!v.ok) return responder({ ok: false, motivo: v.motivo, detalle: v.detalle + ' La reserva actual se mantiene sin cambios.', reserva_actual: vista(r, esPersonal), alternativas: sinAlternativas(v.motivo) ? [] : alternativas(ctx, fecha, hora, personas, zonaPedida, esPersonal, op) });
  const nombre = esPersonal && norm(E.nombre) ? norm(E.nombre) : norm(r.nombre);
  const telefono = esPersonal && telCliente ? telCliente : normTel(r.telefono);
  const clave = claveIdem(telefono, nombre, v.ini);
  if (ctx.activas.some(x => x.id !== r.id && norm(x.clave_idem) === clave)) return responder({ ok: false, motivo: 'ya_reservado', detalle: 'Ya hay otra reserva con ese teléfono/nombre a esa misma hora. La reserva actual se mantiene.' });
  let zonas = ctx.zonasConSitio(v.ini, v.fin, v.personas, zonaPedida || normZona(r.zona), op);
  if (!zonas.length && !zonaPedida) zonas = ctx.zonasConSitio(v.ini, v.fin, v.personas, '', op);
  if (!zonas.length) return responder({ ok: false, motivo: 'sin_disponibilidad', detalle: 'No hay sitio para el cambio solicitado. La reserva actual se mantiene sin cambios.', reserva_actual: vista(r, esPersonal), alternativas: alternativas(ctx, fecha, hora, v.personas, zonaPedida, esPersonal, op) });
  const zona = zonas[0];
  const obs = norm(E.observaciones) ? norm(E.observaciones) : norm(r.observaciones);
  const cambios = { nombre, telefono, fecha: v.fecha, hora: v.hora, inicio_ts: v.ini, fin_ts: v.fin, personas: v.personas, zona, observaciones: obs, clave_idem: clave, version: Number(r.version) + 1, actualizado_ts: nowMs };
  const despues = { ...antes, ...cambios };
  const igual = ['nombre', 'telefono', 'inicio_ts', 'personas', 'zona', 'observaciones'].every(k => String(antes[k] ?? '') === String(despues[k] ?? ''));
  if (igual) return responder({ ok: true, accion: 'sin_cambios', detalle: 'La reserva ya tenía esos datos; no se ha modificado nada.', reserva: vista(r, esPersonal) });
  return [{ json: {
    op: 'reservar', tipo: 'modificar', fila: cambios, reserva_id: r.id, version_actual: Number(r.version), es_personal: esPersonal,
    cola: { codigo: r.codigo, accion: 'modificar', zona, inicio_ts: v.ini, fin_ts: v.fin, personas: v.personas, estado: 'pendiente', creado_ts: nowMs, clave_idem: clave, reserva_id: r.id },
    evento: evento(r.codigo, 'modificada', antes, despues, avisarCliente(despues, 'modificada') || avisarCliente(r, 'modificada'), true),
    resultado_exito: { ok: true, accion: 'reserva_modificada', reserva: vista(despues, esPersonal), antes: vista(r, esPersonal) }
  } }];
}

return responder({ ok: false, motivo: 'accion_desconocida', detalle: 'Acciones: disponibilidad, crear, reservas_cliente, modificar, cancelar, listar, buscar, listar_bloqueos, bloquear, desbloquear.' });
