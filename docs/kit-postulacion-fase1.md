# Kit de Postulación — Especificación Fase 1

Estado: propuesta para revisión. No implementar hasta que el usuario cierre las "Decisiones" del final.

## 1. Objetivo

Reducir a la mitad (o más) el tiempo por postulación **sin asumir riesgo de cuenta ni de detección de bot**.
Desde una oferta del digest, con un clic, el sistema arma un **kit**:

1. CV adaptado a esa oferta (DOCX; PDF según decisión B).
2. Carta de presentación adaptada.
3. Un documento con las **respuestas del formulario** listas para copiar/pegar (datos de contacto, años de
   experiencia, sueldo, idiomas, autorización para trabajar, y las preguntas propias del aviso).

El envío y el llenado del formulario **no** son parte de la Fase 1 (ver "Fuera de alcance").

## 2. Principios (no negociables)

- **Semiautomático: el usuario aprueba y envía.** El sistema prepara, nunca postula solo.
- **El agente nunca inventa respuestas.** Las respuestas salen del master resume o del "banco de respuestas"
  aprobado una vez por el usuario. Si falta un dato, lo marca como `FALTA: revisar`, no lo adivina.
- **Nunca automatizar LinkedIn / Easy Apply** (riesgo de cierre de cuenta).
- **Las preguntas legales (autorización, patrocinio) las responde el usuario**, se guardan en el banco y se reutilizan.
- Cuando llegue la Fase 2 (llenado con Playwright), **el navegador corre en el computador del usuario, no en Render.**

## 3. Lo que ya existe y se reutiliza (no reconstruir)

| Pieza | Dónde | Uso en la Fase 1 |
|---|---|---|
| Adaptar master → oferta | `services/resume_adapter_v2.adapt_resume_data`, `routers/adaptations.py` (`POST /adaptations/`) | Genera el CV adaptado. Ya acepta `job_description` + `job_url`. |
| Master resume | `data/master_hr_technology.json`, `routers/master.py` | Fuente del CV y de varios campos del banco (contacto, idiomas, experiencia). |
| Export DOCX | `routers/export.py` (`GET /export/{adaptation_id}/docx`) | Descarga del CV adaptado. |
| Generador DOCX por plantillas | `services/resume_generator.py` (plantillas `classic`, `iris`) | Reutilizable para la carta si se quiere mismo estilo. |
| Texto del aviso + preguntas | `digest_jobs.description`, `digest_jobs.application_questions` (preguntas de Greenhouse) | Alimenta el CV, la carta y las respuestas sin volver a leer la web. |
| Frontend | `frontend/app/` (`generar`, `history`, `saved`) | Superficie donde se dispara y se descarga el kit. |

## 4. Lo que construimos en la Fase 1

### 4.1 Disparador digest → kit
Hoy las ofertas del digest viven en `digest_jobs` (con `description` y `application_questions`), pero no se
conectan con `adaptations`. Se agrega el puente:

- `POST /kits` con `{ job_url }` (o `job_id`). El backend busca la oferta en `digest_jobs`, toma su
  `description`/`company`/`title`/`application_questions`, crea una `Adaptation` sembrada con ese texto, y crea
  un registro `ApplicationKit` que agrupa CV + carta + respuestas.
- En el **correo del digest**, cada oferta lleva un enlace "Preparar kit" que abre una página del frontend
  (`/kit?job=<url>`) que llama a ese endpoint y muestra el kit para descargar/copiar. (Ver Decisión A.)

### 4.2 Carta de presentación (nuevo)
- Nuevo servicio `services/cover_letter.py`: 1 llamada LLM que, con el master + el texto del aviso, produce una
  carta corta (3–4 párrafos), en el idioma del aviso (es/en), sin inventar logros fuera del master.
- Se guarda en el kit; se exporta en el mismo formato que el CV.

### 4.3 Banco de respuestas (nuevo, el corazón de la Fase 1)
Tabla `answer_bank`: respuestas estándar que el usuario aprueba **una sola vez** y el sistema reutiliza:

- Contacto (nombre, email, teléfono, ciudad, LinkedIn) — se pre-llena del master, el usuario confirma.
- Autorización para trabajar / necesidad de patrocinio (por país: Chile, Canadá) — **respondidas por el usuario**.
- Años de experiencia total y por herramienta (Salesforce, Dynamics 365, Jira, etc.).
- Idiomas y nivel (español nativo, inglés profesional, sin francés).
- Expectativa de sueldo por lista (Chile / Canadá / remoto), disponibilidad, aviso de salida, modalidad.
- Enlaces (portafolio, LinkedIn), pronombres opcionales, etc.

Por oferta, el sistema arma un documento de respuestas:
1. Copia las respuestas estándar del banco que apliquen.
2. Para las **preguntas propias del aviso** (`application_questions` de Greenhouse, o las típicas de Lever/Ashby),
   hace **1 llamada LLM barata** que mapea cada pregunta a una respuesta usando SOLO el banco + el master. Si no
   hay base para responder, escribe `FALTA: responder tú` en vez de inventar.
3. Entrega un `.md`/`.docx` con "Pregunta → Respuesta" para copiar/pegar.

### 4.4 Ensamblado y descarga
`GET /kits/{id}` devuelve el estado y los enlaces de descarga: CV (DOCX/PDF), carta (DOCX/PDF), respuestas (DOCX/MD).
`GET /kits/{id}/zip` opcional: un ZIP con todo, nombrado `Empresa_Puesto/`.

## 5. Modelo de datos (nuevo)

- `answer_bank` (una fila por usuario; es config, no por oferta): JSON con las respuestas estándar + `updated_at`.
- `application_kit`:
  - `id`, `created_at`, `job_url`, `company`, `title`, `list_key`
  - `adaptation_id` (FK a la adaptación del CV)
  - `cover_letter_text`, `cover_letter_path`
  - `answers_json` (pregunta → respuesta, con marcas `FALTA`)
  - `status` (`pending` | `ready` | `error`)
  - `applied_at` (se marca cuando el usuario confirma que postuló; alimenta `applied.csv`/exclusión del digest)

Nota: al marcar "postulé" en un kit, se agrega la fila a la lista de ya-postuladas para que el digest la excluya
(cierra el ciclo con el trabajo que ya hicimos de exclusión por empresa + título).

## 6. Presupuesto de tokens por postulación (objetivo: bajo)

- CV adaptado: 1 llamada LLM (ya existe).
- Carta: 1 llamada LLM corta.
- Respuestas del aviso: 1 llamada LLM corta (solo si el aviso trae preguntas; si no, 0).
- Total típico: **2–3 llamadas**, todas con el mismo pool gratuito (Groq/Gemini) que ya usa el digest.

## 7. Flujo del usuario

1. Llega el digest. El usuario ve una oferta que le interesa y hace clic en "Preparar kit".
2. Se abre la página del kit; en ~segundos tiene CV adaptado + carta + respuestas.
3. Revisa, ajusta lo que quiera, descarga. Abre el portal de la empresa **él mismo**, pega las respuestas, adjunta el CV, y envía.
4. Marca "postulé" → la oferta queda excluida de futuros digests.

## 8. Fuera de alcance (Fase 2 y 3, para después)

- **Fase 2 — llenado asistido con Playwright** en Greenhouse/Lever/Ashby, corriendo en el computador del usuario,
  que llena el formulario y se detiene **antes** de enviar, con captura para que el usuario apriete "Submit".
- **Fase 3 — Workday**, solo después de que la Fase 2 funcione.
- **Nunca** — Easy Apply de LinkedIn automatizado.

## 9. Decisiones para cerrar la Fase 1

- **A. Dónde se dispara "Preparar kit":** (recomendado) enlace en el correo del digest → página del frontend.
  Alternativa: solo desde el frontend (lista de guardados/historial).
- **B. PDF:** el CV hoy es solo DOCX. Opciones: (b1) entregar DOCX en la Fase 1 y dejar PDF para después;
  (b2) agregar LibreOffice headless al Docker y convertir DOCX→PDF; (b3) generar PDF directo con reportlab.
  Recomendado: **b1 ahora**, b2 como seguimiento corto.
- **C. Banco de respuestas:** ¿lo llenamos juntos ahora (contacto, sueldos por lista, autorización CL/CA, idiomas)
  o se parte con un formulario en el frontend para que lo cargues tú?
