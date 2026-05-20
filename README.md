# 📄 Resume Adapter

**Tu resume canadiense como plantilla maestra. Cada oferta genera una versión adaptada — sin romper el formato.**

---

## Cómo funciona

```
1. Cargas tu resume canadiense (DOCX o PDF)  →  Se guarda como FUENTE DE VERDAD
2. Pegas una oferta laboral                  →  IA analiza requisitos y keywords ATS
3. El sistema decide qué secciones adaptar   →  Mínimo necesario: summary, skills, bullets
4. Reescribe SOLO esas secciones             →  Preserva todo el formato canadiense
5. Generas el .docx final                    →  Listo para postular
```

**Regla central del sistema:**
> *"Usa siempre el resume tipo canadiense ya cargado como plantilla maestra. Adapta solo el contenido necesario para la oferta, sin alterar la estructura, el estilo canadiense ni el formato del documento base."*

Esta frase está en el prompt principal del sistema y en cada sub-prompt de reescritura.

---

## Instalación

### Prerrequisitos
- Python 3.11+
- Node.js 18+
- API key de OpenAI o Groq

### 1. Backend

```bash
cd resume-adapter/backend
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp ../.env.example ../.env
# Edita .env y pon tu OPENAI_API_KEY o GROQ_API_KEY
```

### 2. Iniciar backend (Terminal 1)

```bash
# Desde la carpeta resume-adapter/
uvicorn backend.main:app --reload --port 8000
```

### 3. Frontend (Terminal 2)

```bash
cd resume-adapter/frontend
npm install
cp .env.local.example .env.local
npm run dev
```

### 4. Abrir la app

**http://localhost:3000**

---

## Flujo de uso

### Primera vez
1. Sube tu resume maestro canadiense (DOCX recomendado)
2. El sistema detecta automáticamente las secciones (Summary, Skills, Experience, etc.)
3. Las secciones se clasifican en:
   - **✏️ Adaptables**: Summary, Skills, Experience, Projects
   - **🔒 Protegidas**: Education, Certifications, Languages, Contact

### Por cada oferta
1. Pega el job description completo
2. Agrega instrucciones opcionales ("énfasis en liderazgo", "empresa de fintech")
3. Elige el modelo de IA (GPT-4o para mejor calidad, Llama 3 para gratuito)
4. La IA corre un pipeline de 4 etapas:
   - Análisis de la oferta → extrae keywords ATS, seniority, requisitos
   - Selección de bloques → decide cuáles secciones adaptar y por qué
   - Reescritura → una llamada LLM por sección (prompts separados)
   - Construcción del docx → inserta cambios en el documento original
5. Revisa el diff (original vs adaptado por sección)
6. Descarga el `.docx` listo para postular

---

## Estructura del proyecto

```
resume-adapter/
├── backend/
│   ├── main.py                      # FastAPI app
│   ├── config.py                    # Variables de entorno
│   ├── database.py                  # SQLite / SQLAlchemy
│   ├── models/
│   │   ├── master.py                # Resume maestro
│   │   └── adaptation.py            # Una adaptación por oferta
│   ├── routers/
│   │   ├── master.py                # Upload / activate / delete master
│   │   ├── adaptations.py           # Create / list / get adaptations
│   │   └── export.py                # Download adapted .docx
│   ├── services/
│   │   ├── resume_parser.py         # Detecta secciones en DOCX/PDF
│   │   ├── adapter.py               # Pipeline IA (3 etapas)
│   │   ├── docx_builder.py          # Reconstruye el docx in-place
│   │   ├── llm_client.py            # OpenAI / Groq con retry
│   │   └── prompt_loader.py         # Carga prompts desde /prompts
│   └── prompts/                     # Prompts editables por etapa
│       ├── analyze_job.txt           # Etapa 1: análisis de oferta
│       ├── select_blocks.txt         # Etapa 2: selección de secciones
│       ├── adapt_summary.txt         # Etapa 3a: reescritura de summary
│       ├── adapt_skills.txt          # Etapa 3b: reescritura de skills
│       └── adapt_experience.txt      # Etapa 3c: reescritura de experience
├── frontend/
│   ├── app/
│   │   ├── page.tsx                  # Pantalla principal
│   │   └── history/page.tsx          # Historial de adaptaciones
│   └── components/
│       ├── master/MasterUpload.tsx   # Subida del resume maestro
│       ├── master/MasterStatus.tsx   # Estado del maestro activo
│       ├── job/JobForm.tsx           # Input de oferta + config
│       └── result/AdaptationResult.tsx  # Resultado + diff + descarga
└── .env.example
```

---

## Personalizar los prompts

Los prompts están en `backend/prompts/*.txt` y se pueden editar sin tocar código:

| Archivo | Cuándo se usa |
|---------|---------------|
| `analyze_job.txt` | Al recibir una nueva oferta — extrae keywords, requisitos, seniority |
| `select_blocks.txt` | Decide qué secciones adaptar y cuáles dejar igual |
| `adapt_summary.txt` | Reescribe el summary/profile |
| `adapt_skills.txt` | Reordena y reformula la sección de skills |
| `adapt_experience.txt` | Ajusta bullets de experiencia |

---

## Próximos pasos sugeridos

- **Cover letter adapter** — generar carta de presentación usando el mismo resume maestro
- **Score de match** — porcentaje de alineación antes y después de adaptar
- **Múltiples masters** — un master en inglés, otro en francés, para alternar
- **Historial de versiones** — ver todas las adaptaciones por empresa/rol
- **Editor manual** — modificar el texto adaptado antes de generar el docx
- **Export tracking** — saber cuándo descargaste y postulaste cada versión
