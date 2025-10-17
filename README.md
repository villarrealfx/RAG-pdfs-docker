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
| **`rag-core`** | `FastAPI`, `Langchain` | **Núcleo del Backend.** Gestiona la ingesta de documentos, el procesamiento RAG (reescritura, búsqueda híbrida, reranking, consulta a LLM) y la transferencia de respuestas. |
| **`airflow`** | `Airflow` (DAGs) | **Orquestación de Ingesta.** Programa semanalmente la búsqueda y procesamiento pesado de nuevos PDFs. |
| **`frontend`** | `Streamlit` | **Interfaz de Usuario (UI).** Permite a los usuarios realizar consultas, visualizar respuestas y enviar evaluaciones (feedback). |
| **`postgres_app`** | `PostgreSQL` | **Base de Datos de Aplicación.** Almacena metadatos de documentos (hash) y el feedback/evaluación del usuario. |
| **`postgres`** | `PostgreSQL` | **Base de Datos de Airflow.** Almacena la metadata de la orquestación de Airflow. |
| **`qdrant`** | `Qdrant` | **Base de Datos Vectorial.** Almacena los *retrieval_context* semánticos y sus vectores para la recuperación RAG. |

-----

## 💻 Flujo de Trabajo y Funcionalidad (RAG & Ingesta)

El sistema opera bajo dos flujos principales: la **Ingesta de Documentos (vía Airflow)** y la **Consulta del Usuario (vía Frontend)**.

### 1\. Flujo de Ingesta (Airflow Orquestado)

Este proceso se ejecuta mediante un **DAG programado semanalmente** para mantener la Base de Conocimiento actualizada:

1.  **Búsqueda y Verificación:** `airflow` se conecta a `rag-core` para buscar nuevos PDFs en las carpetas de origen.
2.  `rag-core` utiliza **hashes** para verificar si un documento ya fue procesado y genera una lista de pendientes.
3.  **Procesamiento Pesado:** Si hay documentos pendientes, `airflow` desencadena el proceso en `rag-core`.
      * **Limpieza y Estructuración** de los PDFs.
      * **Creación de *retrieval_context* Semánticos** (fragmentos de texto).
      * **Almacenamiento en BBDD:** Los *retrieval_context* y vectores se guardan en **`qdrant`**.
      * **Almacenamiento de Metadatos:** El hash del documento y otros metadatos se guardan en **`postgres_app`**.

### 2\. Flujo de Consulta (Tiempo Real)

1.  **Consulta de Usuario:** El usuario ingresa una pregunta en la interfaz web de **`frontend`** (`Streamlit`).
2.  **Procesamiento en `rag-core`:**
      * **Reescritura de *Query*:** Mejora la consulta inicial para optimizar la búsqueda.
      * **Búsqueda Híbrida:** Recupera *retrieval_context* relevantes de **`qdrant`**.
      * ***Reranker*:** Selecciona los *retrieval_context* más significativos.
      * **Generación de Respuesta:** La *query* optimizada y los *retrieval_context* seleccionados se pasan al **LLM**.
3.  **Respuesta al Usuario:** `rag-core` envía la respuesta del LLM al `frontend`, incluyendo: el texto de la respuesta, el *score* de relevancia, el resultado del *reranker*, el ID del *chunk* y el texto del *chunk* utilizado.
4.  **Feedback del Usuario:** El usuario puede enviar una evaluación. El `frontend` tramita esta evaluación, y **`rag-core`** la almacena en **`postgres_app`**.

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

-----

## 🚀 Despliegue (Próximamente)

*(En esta sección se incluirían los comandos de Docker/Docker Compose una vez que estén definidos, por ejemplo:)*

```bash
# 1. Clonar el repositorio
git clone <URL_DEL_REPOSITORIO>
cd RAG-SCADA-Chat

# 2. Levantar los microservicios con Docker Compose
docker-compose up -d --build
```

**Acceso:**

  * **Frontend (Streamlit):** `http://localhost:8501`
  * **Airflow UI:** `http://localhost:8080`
  * **FastAPI Docs (rag-core):** `http://localhost:8000/docs`

  ---
  ## Nuevo readme (verificar)

  ¡Excelente\! La información sobre el proceso de instalación, el manejo de la base de conocimiento inicial, el *trigger* manual y el archivo de preguntas (`preguntas.json`) son cruciales.

He actualizado la estructura del `README.md` propuesta, añadiendo una sección detallada de **Instalación y Despliegue** con los pasos que has indicado, y he agregado las secciones recomendadas de **Contacto** y **Licencia**.

-----

# 🤖 RAG-SCADA-Chat 💬

Este proyecto implementa un sistema de **Generación Aumentada por Recuperación (RAG)** utilizando **Modelos de Lenguaje Grande (LLMs)** para transformar manuales técnicos en PDF (operación y mantenimiento de sistemas SCADA eléctricos) en una base de conocimiento conversacional y accesible. Su objetivo es proporcionar **respuestas instantáneas, coherentes y exactas** a las consultas de los usuarios, reduciendo significativamente el tiempo de acceso y rastreo de información en la documentación tradicional.

-----

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
| **`rag-core`** | `FastAPI`, `Langchain` | **Núcleo del Backend.** Gestiona la ingesta de documentos, el procesamiento RAG (reescritura, búsqueda híbrida, reranking, consulta a LLM) y la transferencia de respuestas. |
| **`airflow`** | `Airflow` (DAGs) | **Orquestación de Ingesta.** Programa semanalmente la búsqueda y procesamiento pesado de nuevos PDFs. |
| **`frontend`** | `Streamlit` | **Interfaz de Usuario (UI).** Permite a los usuarios realizar consultas, visualizar respuestas y enviar evaluaciones (feedback). |
| **`postgres_app`** | `PostgreSQL` | **Base de Datos de Aplicación.** Almacena metadatos de documentos (hash) y el feedback/evaluación del usuario. |
| **`postgres`** | `PostgreSQL` | **Base de Datos de Airflow.** Almacena la metadata de la orquestación de Airflow. |
| **`qdrant`** | `Qdrant` | **Base de Datos Vectorial.** Almacena los *retrieval_context* semánticos y sus vectores para la recuperación RAG. |

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
    git clone <URL_DEL_REPOSITORIO>
    cd RAG-SCADA-Chat
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

    Esto inicializará todos los servicios (FastAPI, Airflow, Streamlit, Qdrant y PostgreSQL).

### 3\. Carga de Base de Conocimiento Inicial

Para que la aplicación funcione, es necesario cargar los manuales PDF en la carpeta que el servicio `rag-core` monitorea.

1.  **Mover Archivos PDF:**

      * Copia los archivos PDF de la carpeta `Manuales pdfs` a la ruta interna de `rag-core`:
        ```bash
        cp Manuales\ pdfs/* service/rag-core/data/raw/
        ```
      * **Nota de Procesamiento:** Mover **todos** los manuales puede requerir hasta **90 minutos (1 hora y 30 minutos)** en equipos con recursos limitados. Para una prueba inicial rápida, se recomienda mover solo **1 o 2 manuales**.

2.  **Lanzar el *Trigger* de Ingesta:**

      * Una vez que los archivos están en la carpeta, dirígete a la interfaz web de Airflow: `http://localhost:8080`.
      * Inicia sesión con las credenciales configuradas en el `.env`.
      * Busca el DAG llamado **`scada_rag_ingestion_dag`** y lánzalo manualmente (*trigger*).
      * Este proceso se conectará con `rag-core` para iniciar la limpieza, *chunking* y almacenamiento vectorial en **Qdrant**.

### 4\. Consultas y Evaluación

1.  **Acceder al Frontend:** Una vez completado el procesamiento del DAG, accede a la interfaz de chat: `http://localhost:8501`.
2.  **Realizar Consultas:** Utiliza el chat para realizar preguntas sobre el contenido de los manuales procesados.
3.  **Preguntas de Referencia:** El archivo **`preguntas.json`** contiene un set de preguntas formuladas por un experto en SCADA SDM. Utiliza estas preguntas como referencia para:
      * Verificar las respuestas esperadas.
      * Ejecutar los *scripts* de **Deepeval** para la evaluación de la calidad RAG y LLM.

-----

## ✨ Características Destacadas

  * **Multilenguaje:** Capacidad para **distinguir el idioma** de la consulta y entregar la respuesta en el mismo idioma (**probado en Inglés y Español**).
  * **Evaluación y Calidad (Deepeval):** Incluye capacidades para realizar **evaluación RAG y LLM** utilizando la librería `deepeval`, asegurando la **coherencia y exactitud** de las respuestas.
  * **Trazabilidad:** La respuesta incluye metadatos (ID de *chunk*, texto de *chunk*) que permiten al usuario y al sistema rastrear la fuente de la información.

-----

## 🛠️ Tecnologías Utilizadas

`Postgres`, `Qdrant`, `Airflow`, `Streamlit`, `FastAPI`, `LangChain`, `FastEmbed`, `Docker`, `Deepeval`.

-----

## 📞 Contacto

Si tienes preguntas, sugerencias o quieres colaborar con el proyecto, puedes contactar al desarrollador principal a través de:

  * **Nombre:** Carlos Villarreal P.
  * **Correo Electrónico:** `villarreal.fx@gmail.com`
  * **LinkedIn:** `[Tu Perfil de LinkedIn]`

-----

## 📜 Licencia

Este proyecto está bajo la Licencia **[Indica el tipo de licencia, e.g., MIT, Apache 2.0]**. Consulta el archivo `LICENSE` para más detalles.

***

## 🔬 Guía de Uso y Demostración

Para una demostración visual y un recorrido paso a paso sobre cómo usar la aplicación, desde el lanzamiento del *trigger* de Airflow hasta la realización de consultas en el *frontend* y la evaluación RAG, consulta nuestro tutorial detallado:

➡️ **[TUTORIAL COMPLETO DE USO Y VALIDACIÓN](TUTORIAL.md)**

En el tutorial encontrarás:
* Capturas de pantalla del *trigger* manual de Airflow.
* Ejemplos de consultas utilizando las preguntas de `preguntas.json`.
* Cómo se visualiza el *feedback* y la trazabilidad de los *retrieval_context* en la interfaz de usuario.


---

## Qwen

# Sistema de Consulta de Manuales Técnicos basado en RAG

## Índice

- [Descripción General](#descripción-general)
- [Arquitectura del Proyecto](#arquitectura-del-proyecto)
  - [Servicio `rag-core`](#servicio-rag-core)
  - [Servicio `airflow`](#servicio-airflow)
  - [Servicio `frontend`](#servicio-frontend)
  - [Servicio `postgres`](#servicio-postgres)
  - [Servicio `postgres_app`](#servicio-postgres_app)
  - [Servicio `qdrant`](#servicio-qdrant)
- [Tecnologías Utilizadas](#tecnologías-utilizadas)
- [Características Especiales](#características-especiales)
- [Instalación](#instalación)
- [Uso](#uso)
- [Evaluación del Sistema](#evaluación-del-sistema)
- [Contribuciones](#contribuciones)
- [Licencia](#licencia)

---

## Descripción General

Este proyecto aborda el desafío de acceder rápidamente a la información contenida en manuales de mantenimiento, operación y bitácoras técnicas, comúnmente almacenados en archivos PDF, lo que dificulta su consulta eficiente. Utilizando tecnologías de vanguardia como **RAG (Retrieval-Augmented Generation)** y **Modelos de Lenguaje de Gran Tamaño (LLMs)**, se sistematiza esta información en una **base de conocimiento** consultable a través de un **chat interactivo**.

La aplicación proporciona respuestas específicas, coherentes, exactas e instantáneas, mejorando significativamente la experiencia del usuario. Se ha aplicado específicamente a manuales de operación y mantenimiento de un sistema **SCADA** para el control y supervisión de sistemas eléctricos de transmisión y generación.

El sistema está construido como una arquitectura de **microservicios** que se ejecutan en contenedores **Docker**. Incluye un proceso de **limpieza y procesamiento de PDFs**, almacenamiento en bases de datos vectoriales y relacionales, y una interfaz web intuitiva.

---

## Arquitectura del Proyecto

El sistema se compone de los siguientes servicios:

### Servicio `rag-core`

Es el **núcleo** de la aplicación. Es una **API construida con FastAPI** que maneja toda la lógica de backend:

- **Búsqueda y verificación de documentos**: Busca PDFs en carpetas, verifica si ya han sido procesados usando un hash y mantiene una lista de documentos pendientes.
- **Procesamiento de documentos**: Limpia, estructura, crea *retrieval_context* semánticos y los almacena en la base de datos vectorial (Qdrant).
- **Almacenamiento de metadatos**: Guarda el hash del documento en PostgreSQL.
- **Procesamiento de consultas**: Recibe consultas del frontend, realiza reescritura de la *query*, búsqueda híbrida en la base de datos vectorial, aplica *reranking*, selecciona los *retrieval_context* más relevantes y los envía junto con la consulta a un LLM.
- **Respuesta del LLM**: Recibe la respuesta del LLM y la transfiere al frontend, incluyendo métricas como *score*, *reranker*, ID del *chunk* y su texto.
- **Evaluación del usuario**: Recibe y almacena en PostgreSQL la evaluación que el usuario proporciona sobre la respuesta.

### Servicio `airflow`

Orquesta tareas de procesamiento mediante un **DAG programado** (por ejemplo, semanalmente):

- **Sincronización con `rag-core`**: Consulta si hay nuevos documentos para procesar.
- **Procesamiento pesado**: Si existen documentos pendientes, coordina con `rag-core` para iniciar el procesamiento detallado de PDFs.

### Servicio `frontend`

Es la **interfaz web** desarrollada con **Streamlit**:

- **Consulta del usuario**: Presenta una interfaz donde el usuario puede realizar preguntas.
- **Visualización de respuestas**: Muestra la respuesta recibida de `rag-core`.
- **Evaluación del usuario**: Permite al usuario evaluar la calidad de la respuesta y enviar esa evaluación a `rag-core`.

### Servicio `postgres`

Base de datos **PostgreSQL** dedicada al almacenamiento de metadatos y estado de los **workflows de Airflow**.

### Servicio `postgres_app`

Base de datos **PostgreSQL** dedicada al almacenamiento de **datos de la aplicación**, incluyendo **feedback de usuarios**.

### Servicio `qdrant`

**Base de datos vectorial** utilizada para almacenar los *retrieval_context* semánticos y sus representaciones vectoriales, facilitando la recuperación eficiente de información relevante.

---

## Tecnologías Utilizadas

- **FastAPI**: Framework web para la API backend.
- **Streamlit**: Framework para la interfaz web.
- **LangChain**: Framework para trabajar con LLMs y RAG.
- **FastEmbedding**: Para la generación de embeddings.
- **Qdrant**: Base de datos vectorial.
- **PostgreSQL**: Base de datos relacional para metadatos y feedback.
- **Apache Airflow**: Orquestador de flujos de trabajo.
- **Docker**: Contenerización de microservicios.
- **DeepEval**: Para la evaluación del sistema RAG y LLM.
- **Otras**: Python, etc.

---

## Características Especiales

- **Soporte multilenguaje**: El sistema puede detectar el idioma de la consulta (probado en **Inglés** y **Español**) y responder en el mismo idioma.
- **Evaluación continua**: Integración de **DeepEval** para evaluar la calidad del sistema RAG y LLM.
- **Almacenamiento persistente**: Uso de PostgreSQL para metadatos y feedback, y Qdrant para información vectorizada.
- **Automatización**: Procesamiento de nuevos documentos gestionado por un DAG de Airflow.

---

## Instalación

1. Clona este repositorio:

   ```bash
   git clone <URL_DEL_REPOSITORIO>
   cd <NOMBRE_DEL_REPOSITORIO>