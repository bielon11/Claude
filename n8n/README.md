# La Taberna del Puerto · Reservas con secretario, WhatsApp y teléfono (n8n)

Ampliación del chatbot «Chatbot de FAQ/reservas en web o WhatsApp» (id `SHxeVLKbsVys72B0`) con:

- un **sistema común de reservas** en Data Tables de n8n (sustituye a Google Sheets),
- un **secretario interno** por WhatsApp (texto y notas de voz) con permisos por rol,
- un **agente telefónico** (capa de voz en tiempo real externa) conectado a las mismas reglas,
- **avisos** al personal, **copia en Google Calendar**, **historial** y **gestión de errores**.

El chatbot original **sigue activo y sin tocar** hasta que se haga el cambio (ver «Puesta en marcha»).

## Workflows

| Workflow | Id | Estado | Qué hace |
|---|---|---|---|
| Reservas · Entrada WhatsApp (enrutador) | `JOuf3TPXhK4f26WC` | **Sin publicar** (sustituirá al chatbot) | Único disparador de WhatsApp. Anti-duplicados por `wamid`, identifica al remitente (`res_personal`), transcribe notas de voz y reparte a Secretario o Chatbot de clientes. Tiene una *Entrada de pruebas* (POST con clave). |
| Reservas · Chatbot clientes WhatsApp | `xDiHbTj31JLz7JO2` | Publicado (sub-workflow) | Mismo prompt, FAQ y tono del chatbot original; sus herramientas usan el Motor común (origen `whatsapp`). |
| Reservas · Secretario interno | `RISmUsfFDEmfPzUL` | Publicado (sub-workflow) | Asistente para el personal: consultas con totales, crear / modificar / cancelar, bloqueos de agenda. |
| Reservas · Herramientas agente telefónico | `9zC6asNjgBYdPKug` | Publicado | Webhook `POST /webhook/reservas-voz` (cabecera `x-clave`) para las *server tools* del agente de voz. |
| Reservas · Motor común | `CyBH9RLyq6B4h71T` | Publicado (sub-workflow) | **Única** implementación de reglas, permisos, anti-colisión, idempotencia e historial. |
| Reservas · Avisos y calendario | `MjdJ51wJEZu5IsFq` | Publicado | Tras guardar: aviso WhatsApp al personal (si procede) y copia en Google Calendar. Reintenta cada 30 min. Sus fallos solo se anotan. |
| Reservas · Errores | `9gvm7mnjStlSTTlP` | Publicado | *Error workflow* de todos los anteriores: registra y avisa. |
| Reservas · Utilidades (ejecución manual) | `sEhZkcXM1Kvp3jDZ` | No publicar | Migración idempotente desde la hoja antigua; preparación de la puesta en marcha. |
| Reservas · Banco de pruebas (no activar) | `woLE9sOzejpGJrSL` | No publicar | Llama al motor con cualquier entrada, solo para pruebas. |

```
WhatsApp ──► Enrutador ──┬─ personal activo ──► Secretario interno ─┐
                         └─ resto ────────────► Chatbot clientes ───┤
Teléfono ─► ElevenLabs (voz) ─► Herramientas agente telefónico ─────┤
                                                                     ▼
                                                           Reservas · Motor común
                                                           (Data Tables res_*)
                                                                     │ (sin esperar)
                                                                     ▼
                                                     Avisos y calendario · Errores
```

## Almacenamiento (Data Tables del proyecto)

| Tabla | Para qué |
|---|---|
| `res_reservas` | Reservas. `codigo` (R…), `origen` (whatsapp / llamada / secretario), `creado_por`, `clave_idem`, `version`. |
| `res_eventos` | Historial de cambios (antes/después, origen, actor) **y** cola de avisos (`aviso_estado`, `calendario_estado`). |
| `res_cierres` | Bloqueos de agenda (cerrar una zona o retener plazas en un día/franja). |
| `res_cola` | Bloqueos provisionales técnicos (anti-colisión). No tocar. |
| `res_config` | Horarios, cierres, capacidades, duración, avisos, calendarios, claves. **Aquí se cambian las reglas.** |
| `res_personal` | Personal autorizado: `telefono` (con 34), `nombre`, `rol` (`lectura` / `gestion` / `admin`), `activo`, `recibe_avisos`. |
| `res_mensajes` | Ids de mensajes de WhatsApp ya recibidos (anti-duplicados). |

La memoria de los agentes **no** guarda reservas: solo el hilo de la conversación (separado por teléfono; el secretario con clave `sec-<teléfono>`).

## Reglas y garantías (todas en el Motor común)

- **Mismas reglas para los tres canales**: franjas de hora de inicio por día, días cerrados, antelación mínima (no aplica al personal), máximo por reserva (el personal puede superar el máximo automático pero nunca el aforo), aforo simultáneo por zona con duración y margen, bloqueos de agenda.
- **Último hueco a la vez desde dos canales**: cada alta/cambio escribe un bloqueo provisional en `res_cola`, relee la cola y luego las reservas, y solo confirma si cabe contando los bloqueos que entraron antes. El otro recibe `ocupado_simultaneamente` con alternativas.
- **Cambios concurrentes sobre la misma reserva**: la actualización filtra por `id` + `version`; si alguien la cambió antes, no se aplica nada.
- **Reintentos / webhooks repetidos**: el enrutador descarta `wamid` repetidos; además `clave_idem` (teléfono o nombre + día/hora) hace que un segundo «crear» devuelva la reserva existente sin duplicar.
- **Confirmar solo lo guardado**: los asistentes solo dicen «confirmada» si el motor devuelve `ok=true`.
- **Reserva ≠ aviso**: avisos y Calendar se lanzan después de guardar, sin esperar; si fallan, se anota en `res_eventos` y la reserva no se repite.
- **Fechas**: «hoy/mañana» con `Europe/Madrid` (calendario de 8 días en cada mensaje y resolución en el motor).
- **Permisos reales**: el teléfono del actor lo pone el canal (no la IA) y el motor comprueba `res_personal` y el rol en cada acción.

| Rol | Puede |
|---|---|
| `lectura` | consultar reservas y totales, buscar, disponibilidad, ver bloqueos |
| `gestion` | lo anterior + crear, modificar y cancelar cualquier reserva |
| `admin` | lo anterior + bloquear / desbloquear agenda |

**Cuándo se avisa al personal** (`recibe_avisos=true`): reservas, cambios o cancelaciones de clientes **para hoy**, grupos ≥ `aviso_grupo_desde` (8), cancelaciones de clientes para **mañana**, llamadas que piden una persona y errores. El resto queda disponible para consultar al secretario.

## Cómo usar el secretario

Escribid o mandad una nota de voz al número de WhatsApp del restaurante desde un teléfono dado de alta en `res_personal` (activo):

- «¿Qué reservas tengo hoy?» · «¿Cuántos vienen a interior y cuántos a terraza?» · «¿Qué hay mañana por la noche?»
- «Añade una reserva para cuatro personas a las nueve a nombre de Lucía» (preguntará lo que falte o lo que haya supuesto).
- «Cámbiala a terraza» / «Cambia la R7KM3 a las 21:30».
- «Cancela la reserva de Marta» → pide confirmación → «sí».
- (admin) «Cierra la terraza esta noche por lluvia» → confirmación → avisa de reservas afectadas (no las cancela solo).

Cada reserva se muestra con su **código** (R…), útil para referirse a ella.

## Agente telefónico

Recomendación: **ElevenLabs Agents** (voz en español muy natural, *server tools* por webhook, variables `system__caller_id`, transferencia `transfer_to_number`) con un número **Twilio** o un **SIP trunk**.
Conexión del teléfono actual: desvío (incondicional o si no contestan / comunica) del número del restaurante al número del agente; la transferencia a persona va a otro número (móvil del encargado o una segunda línea) para evitar bucles.

- Prompt: `voz/prompt_agente_voz.md`.
- Herramientas: `voz/elevenlabs_agente.json` (URL `https://lavenderblush-okapi-857486.hostingersite.com/webhook/reservas-voz`, cabecera `x-clave` = `res_config.clave_voz`).
- Seguridad: ver/modificar/cancelar solo con el **número que llama**; con número oculto, solo crear (con teléfono de contacto) o transferir.

## Puesta en marcha (pendiente de vuestra decisión)

1. Dar de alta al personal real en `res_personal` (teléfono con 34, rol, `activo=true`, `recibe_avisos` a quien deba recibir avisos). Los usuarios `PRUEBA …` ya están desactivados; podéis borrarlos.
2. Ajustar en `res_config` los datos reales: `capacidad_interior` / `capacidad_terraza` (ahora 5 de prueba), horarios, cierres.
3. *Utilidades → Migrar desde Google Sheets* (repetible).
4. **Despublicar** «Chatbot de FAQ/reservas en web o WhatsApp» y **publicar** «Reservas · Entrada WhatsApp (enrutador)» (solo puede haber un disparador de WhatsApp activo).
5. Repetir *Migrar desde Google Sheets* por si entró alguna reserva entre medias.
6. Vuelta atrás: despublicar el enrutador y volver a publicar el chatbot original.

## Código fuente y pruebas

- `motor/` código de los nodos Code del motor (librería común + evaluar / verificar / comprobar).
- `avisos/`, `voz/`, `migracion/` código de los demás nodos Code.
- `prompts/` instrucciones de los agentes.
- `gen/` generadores del código Workflow SDK con el que se crearon los workflows.
- `tests/` pruebas locales del motor: `cd tests && npm install && npm test` (29 casos: reglas, permisos, duplicados, concurrencia, bloqueos).
