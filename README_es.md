# 🤖 RAG-SCADA-Chat 💬

Este proyecto implementa un sistema de **Generación Aumentada por Recuperación (RAG)** utilizando **Modelos de Lenguaje Grande (LLMs)** para transformar manuales técnicos en PDF (operación y mantenimiento de sistemas SCADA eléctricos) en una base de conocimiento conversacional y accesible. Su objetivo es proporcionar **respuestas instantáneas, coherentes y exactas** a las consultas de los usuarios, reduciendo significativamente el tiempo de acceso y rastreo de información en la documentación tradicional.

## 📌 Caso de Uso e Impacto

En la **industria de transmisión y generación eléctrica**, el acceso rápido a la información de los manuales de operación y mantenimiento de sistemas SCADA es crucial. La dificultad de rastrear datos específicos en extensos archivos PDF se elimina al sistematizar esta documentación como una **Base de Conocimiento** a la que se accede mediante un chat inteligente.

El sistema se enfoca en manuales de **SCADA para el control y supervisión de sistemas eléctricos**, ofreciendo:

  * **Acceso Instantáneo:** Consultas a través de un chat en lugar de búsqueda manual en PDFs.
  * **Información Específica:** Respuestas directas, coherentes y exactas potenciadas por LLMs.
  * **Eficiencia Operacional:** Ahorro de tiempo significativo para personal de mantenimiento y operación.

-----

## ⚙️ Arquitectura del Proyecto y Microservicios

El proyecto está diseñado como una aplicación de microservicios contenerizada con **Docker**, asegurando escalabilidad y fácil despliegue.

| Servicio | Tecnología | Descripción de Funcionalidad Principal |
| :--- | :--- | :--- |
| **`rag-core`** | `FastAPI` `Langchain` `DeepEval` `DeepSeep` `Gemini` `fastembed` `PyMuPDF` | **Núcleo del Backend.** Gestiona la ingesta de documentos, el procesamiento RAG (reescritura, búsqueda híbrida, reranking, consulta a LLM) y la transferencia de respuestas. |
| **`airflow`** | `Airflow` (DAGs) | **Orquestación de Ingesta.** Programa semanalmente la búsqueda y procesamiento pesado de nuevos PDFs. |
| **`frontend`** | `Streamlit` `Pandas` `Ploty` | **Interfaz de Usuario (UI).** Permite a los usuarios realizar consultas, visualizar respuestas y enviar evaluaciones (feedback). |
| **`postgres_app`** | `PostgreSQL` | **Base de Datos de Aplicación.** Almacena metadatos de documentos (hash) y el feedback/evaluación del usuario. |
| **`postgres`** | `PostgreSQL` | **Base de Datos de Airflow.** Almacena la metadata de la orquestación de Airflow. |
| **`qdrant`** | `Qdrant` | **Base de Datos Vectorial.** Almacena los *retrieval_context* semánticos y sus vectores para la recuperación RAG. |

-----

## 💻 Flujo de Trabajo y Funcionalidad (RAG & Ingesta)

El sistema opera bajo tres flujos principales: la **Ingesta de Documentos (vía Airflow), La automatización de las Evaluaciones continua (vía Airflow) y la Consulta del Usuario (vía Frontend)**.

### 1\. Flujo de Ingesta (Airflow Orquestado)

Este proceso se ejecuta mediante un **DAG programado semanalmente** para mantener la Base de Conocimiento actualizada:

1.  **Búsqueda y Verificación:** `airflow` se conecta a `rag-core` para buscar nuevos PDFs en las carpetas de origen.
2.  `rag-core` utiliza **hashes** para verificar si un documento ya fue procesado y genera una lista de pendientes.
3.  **Procesamiento Pesado:** Si hay documentos pendientes, `airflow` desencadena el proceso en `rag-core`.
      * **Limpieza y Estructuración** de los PDFs.
      * **Creación de *retrieval_context* Semánticos** (fragmentos de texto).
      * **Almacenamiento en BBDD:** Los *retrieval_context* y vectores se guardan en **`qdrant`**.
      * **Almacenamiento de Metadatos:** El hash del documento y otros metadatos se guardan en **`postgres_app`**.

### 2\. Flujo para Monitoreo y Evaluación Continua (Airflow Orquestado)
Este proceso se ejecuta mediante un **DAG programado semanalmente** para la evaluación continua del RAG
1. Llama a endpoints de `rag-core` para obtener feedback de la semana pasada y las anotaciones de experto correspondientes.
2. Llama al endpoint de `rag-core` que ejecuta la suite de evaluación con los datos obtenidos previamente.
3. Genera reporte final de la ejecución de la evaluación y almacena en Base de datos.

### 3\. Flujo de Consulta (Tiempo Real)

1.  **Consulta de Usuario:** El usuario ingresa una pregunta en la interfaz web de **`frontend`** (`Streamlit`).
2.  **Procesamiento en `rag-core`:**
      * **Reescritura de *Query*:** Mejora la consulta inicial para optimizar la búsqueda.
      * **Búsqueda Híbrida:** Recupera *retrieval_context* relevantes de **`qdrant`**.
      * ***Reranker*:** Selecciona los *retrieval_context* más significativos.
      * **Generación de Respuesta:** La *query* optimizada y los *retrieval_context* seleccionados se pasan al **LLM**.
3.  **Respuesta al Usuario:** `rag-core` envía la respuesta del LLM al `frontend`, incluyendo: el texto de la respuesta, el *score* de relevancia, el resultado del *reranker*, el ID del *chunk* y el texto del *chunk* utilizado.
4.  **Feedback del Usuario:** El usuario puede enviar una evaluación. El `frontend` tramita esta evaluación, y **`rag-core`** la almacena en **`postgres_app`**.
5. **La UI de consulta** interactua con el backend `rag-core` para obtener la data necesaria para la creación de Daschboard donde se expone de manera grafica el comportamiento histórico del sistema RAG a través de las evaluaciones, actualizaciones feedback de usuarios y expertos.

-----

## ✨ Características Destacadas

  * **Multilenguaje:** Capacidad para **distinguir el idioma** de la consulta y entregar la respuesta en el mismo idioma (**probado en Inglés y Español**).
  * **Evaluación y Calidad (Deepeval):** Incluye capacidades para realizar **evaluación RAG y LLM** utilizando la librería `deepeval`, asegurando la **coherencia y exactitud** de las respuestas.
  * **Trazabilidad:** La respuesta incluye metadatos (ID de *chunk*, texto de *chunk*) que permiten al usuario y al sistema rastrear la fuente de la información.

-----

## 🛠️ Tecnologías Utilizadas

Las siguientes tecnologías son la base de este proyecto de microservicios:

  * **Backend:** `FastAPI`
  * **Orquestación:** `Airflow`
  * **Frontend:** `Streamlit`
  * **BBDD Vectorial:** `Qdrant`
  * **BBDD Relacional:** `PostgreSQL`
  * **Framework RAG:** `LangChain`
  * **Embeddings:** `FastEmbed`
  * **Contenerización:** `Docker`
  * **Evaluación:** `Deepeval`
  * **LLMs** `DeepSeep` `Gemini`

-----

## 🚀 Instalación y Despliegue

Sigue los siguientes pasos para levantar la aplicación y procesar la base de conocimiento inicial:

### 1\. Requisitos Previos

Asegúrate de tener instalado:

  * **Docker**
  * **Docker Compose**

### 2\. Pasos de Despliegue

1.  **Clonar el Repositorio:**

   ```bash
   git clone https://github.com/villarrealfx/RAG-pdfs-docker.git
   cd RAG-pdfs-docker
   ```

2.  **Configurar Variables de Entorno:**

      * Copia el archivo de ejemplo y reconfíguralo:
        ```bash
        cp .env.example .env
        ```
      * **Edita el archivo `.env`** para completar las variables necesarias (puertos, credenciales de bases de datos, claves de APIs si son requeridas por los LLMs, etc.).

3.  **Levantar los Microservicios:**

    ```bash
    docker-compose up -d --build
    ```

    Esto inicializará todos los servicios `rag-core` (FastAPI), `airflow`, `frontend` (Streamlit), `Qdrant` y `PostgreSQL`.

### 3\. Carga de Base de Conocimiento Inicial

Para que la aplicación funcione, es necesario cargar los manuales PDF en la carpeta que el servicio `rag-core` monitorea.

1.  **Mover Archivos PDF:**

      * Copia los archivos PDF de la carpeta `Manuales pdfs` a la ruta interna de `rag-core`:
        ```bash
        cp manuales_pdfs/* service/rag-core/data/raw/
        ```
      * **Nota de Procesamiento:** 
      Mover **todos** los manuales puede requerir hasta **90 minutos (1 hora y 30 minutos)** en equipos con recursos limitados. Para una prueba inicial rápida, se recomienda mover solo **1 o 2 manuales**.
      Todos los modelos se cargan al inicio por lo que el arranque del sistema puede tardar algunos minutos.

2.  **Lanzar el *Trigger* de Ingesta:**

      * Una vez que los archivos están en la carpeta, dirígete a la interfaz web de Airflow: `http://localhost:8080`.
      * Inicia sesión con las credenciales configuradas en el `.env`.
      * Busca el DAG llamado **`rag_ingestion_api_orchestrator`** y lánzalo manualmente (*trigger*).
      * Este proceso se conectará con `rag-core` para iniciar la limpieza, *chunking* y almacenamiento vectorial en **Qdrant**.

### 4\. Consultas y Evaluación

1.  **Acceder al Frontend:** Una vez completado el procesamiento del DAG, accede a la interfaz de chat: `http://localhost:8501`.
2.  **Realizar Consultas:** Utiliza el chat para realizar preguntas sobre el contenido de los manuales procesados.
3.  **Preguntas de Referencia:** El archivo **`questions.json`** contiene un set de preguntas formuladas por un experto en SCADA SDM. Utiliza estas preguntas como referencia para:
      * Verificar las respuestas esperadas.
      * Ejecutar los *scripts* de **Deepeval** para la evaluación de la calidad RAG y LLM.
        * En una terminal ingresa al contenedor de rag-core
        ```bash
        docker exec -it rag-core bash
        ```
        * Una vez en el bash del contenedor corre los test de deepeval como sigue
        ```bash
        deepeval test run src/rag_pdf_processor/evaluations/test_deepeval_01.py
        ```
        y/o
        ```bash
        deepeval test run src/rag_pdf_processor/evaluations/test_geval.py
        ```

-----

## 📞 Contacto

Si tienes preguntas, sugerencias o quieres colaborar con el proyecto, puedes contactar al desarrollador principal a través de:

  * **Nombre:** Carlos Villarreal P.
  * **Correo Electrónico:** `villarreal.fx@gmail.com`
  * **LinkedIn:** `https://www.linkedin.com/in/carlos-villarreal-paredes/`

-----

## 🔬 Guía de Uso y Demostración

Para una demostración visual y un recorrido paso a paso sobre cómo usar la aplicación, desde el lanzamiento del *trigger* de Airflow hasta la realización de consultas en el *frontend* y la evaluación RAG, consulta nuestro tutorial detallado:

➡️ **[TUTORIAL COMPLETO DE USO Y VALIDACIÓN](TUTORIAL.md)**

En el tutorial encontrarás:
* Capturas de pantalla del *trigger* manual de Airflow.
* Ejemplos de consultas utilizando las preguntas de `preguntas.json`.
* Cómo se visualiza el *feedback* y la trazabilidad de los *retrieval_context* en la interfaz de usuario.

---