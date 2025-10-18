# 🤖 RAG-SCADA-Chat 💬

This project implements a **Retrieval-Augmented Generation (RAG)** system using **Large Language Models (LLMs)** to transform technical PDF manuals (operation and maintenance of electrical SCADA systems) into a conversational and accessible knowledge base. Its objective is to provide **instant, coherent, and accurate responses** to user queries, significantly reducing the time required to access and search for information in traditional documentation.

## 📌 Use Case and Impact

In the **electrical transmission and generation industry**, rapid access to information from SCADA system operation and maintenance manuals is crucial. The difficulty of tracking specific data in extensive PDF files is eliminated by systematizing this documentation as a **Knowledge Base** accessed through an intelligent chat interface.

The system focuses on **SCADA manuals for controlling and supervising electrical systems**, offering:

* **Instant Access:** Queries through a chat interface instead of manual PDF searches
* **Specific Information:** Direct, coherent, and accurate responses powered by LLMs
* **Operational Efficiency:** Significant time savings for maintenance and operations personnel

-----

## ⚙️ Project Architecture and Microservices

The project is designed as a containerized microservices application using **Docker**, ensuring scalability and easy deployment.

| Service | Technology | Main Functionality Description |
| :--- | :--- | :--- |
| **`rag-core`** | `FastAPI` `Langchain` `DeepEval` `DeepSeek` `Gemini` `fastembed` `PyMuPDF` | **Backend Core.** Manages document ingestion, RAG processing (query rewriting, hybrid search, reranking, LLM querying), and response delivery. |
| **`airflow`** | `Airflow` (DAGs) | **Ingestion Orchestration.** Schedules weekly search and heavy processing of new PDFs. |
| **`frontend`** | `Streamlit` `Pandas` `Plotly` | **User Interface (UI).** Allows users to submit queries, view responses, and provide evaluations (feedback). |
| **`postgres_app`** | `PostgreSQL` | **Application Database.** Stores document metadata (hash) and user feedback/evaluations. |
| **`postgres`** | `PostgreSQL` | **Airflow Database.** Stores Airflow orchestration metadata. |
| **`qdrant`** | `Qdrant` | **Vector Database.** Stores semantic contexts and their vectors for RAG retrieval. |

-----

## 💻 Workflow and Functionality (RAG & Ingestion)

The system operates through three main workflows: **Document Ingestion (via Airflow), Continuous Evaluation Automation (via Airflow), and User Query (via Frontend)**.

### 1. Ingestion Flow (Airflow Orchestrated)

This process runs via a **weekly scheduled DAG** to keep the Knowledge Base updated:

1. **Search and Verification:** `airflow` connects to `rag-core` to search for new PDFs in source folders
2. `rag-core` uses **hashes** to verify if a document was already processed and generates a pending list
3. **Heavy Processing:** If there are pending documents, `airflow` triggers the process in `rag-core`
   * **Cleaning and Structuring** of PDFs
   * **Creation of Semantic Contexts** (text chunks)
   * **Database Storage:** Contexts and vectors are stored in **`qdrant`**
   * **Metadata Storage:** Document hash and other metadata are stored in **`postgres_app`**

### 2. Continuous Monitoring and Evaluation Flow (Airflow Orchestrated)

This process runs via a **weekly scheduled DAG** for continuous RAG evaluation:

1. Calls `rag-core` endpoints to retrieve feedback from the previous week and corresponding expert annotations
2. Calls the `rag-core` endpoint that executes the evaluation suite with the previously obtained data
3. Generates a final evaluation execution report and stores it in the database

### 3. Query Flow (Real-Time)

1. **User Query:** The user enters a question in the **`frontend`** web interface (`Streamlit`)
2. **Processing in `rag-core`:**
   * **Query Rewriting:** Enhances the initial query to optimize search
   * **Hybrid Search:** Retrieves relevant contexts from **`qdrant`**
   * **Reranker:** Selects the most significant contexts
   * **Response Generation:** The optimized query and selected contexts are passed to the **LLM**
3. **Response to User:** `rag-core` sends the LLM's response to the `frontend`, including: the response text, relevance score, reranker result, chunk ID, and the text of the chunk used
4. **User Feedback:** The user can submit an evaluation. The `frontend` processes this evaluation, and **`rag-core`** stores it in **`postgres_app`**
5. **The Query UI** interacts with the `rag-core` backend to obtain the necessary data for creating dashboards that graphically display the historical behavior of the RAG system through evaluations, updates, and user/expert feedback

-----

## ✨ Key Features

* **Multilingual:** Capability to **detect the language** of the query and deliver the response in the same language (**tested in English and Spanish**)
* **Evaluation and Quality (Deepeval):** Includes capabilities for **RAG and LLM evaluation** using the `deepeval` library, ensuring response **coherence and accuracy**
* **Traceability:** The response includes metadata (chunk ID, chunk text) that allows the user and the system to trace the source of the information

-----

## 🛠️ Technologies Used

The following technologies form the foundation of this microservices project:

* **Backend:** `FastAPI`
* **Orchestration:** `Airflow`
* **Frontend:** `Streamlit`
* **Vector Database:** `Qdrant`
* **Relational Database:** `PostgreSQL`
* **RAG Framework:** `LangChain`
* **Embeddings:** `FastEmbed`
* **Containerization:** `Docker`
* **Evaluation:** `Deepeval`
* **LLMs:** `DeepSeek` `Gemini`

-----

## 🚀 Installation and Deployment

Follow these steps to set up the application and process the initial knowledge base:

### 1. Prerequisites

Ensure you have installed:

* **Docker**
* **Docker Compose**

### 2. Deployment Steps

1. **Clone the Repository:**

   ```bash
   git clone <REPOSITORY_URL>
   cd RAG-SCADA-Chat
   ```

2. **Configure Environment Variables:**

   * Copy the example file and reconfigure it:
     ```bash
     cp .env.example .env
     ```
   * **Edit the `.env` file** to complete the necessary variables (ports, database credentials, API keys if required by the LLMs, etc.)

3. **Start the Microservices:**

   ```bash
   docker-compose up -d --build
   ```

   This will initialize all services: `rag-core` (FastAPI), `airflow`, `frontend` (Streamlit), `Qdrant`, and `PostgreSQL`

### 3. Initial Knowledge Base Loading

For the application to function, it's necessary to load the PDF manuals into the folder monitored by the `rag-core` service.

1. **Move PDF Files:**

   * Copy the PDF files from the `Manuales pdfs` folder to the internal path of `rag-core`:
     ```bash
     cp manuales_pdfs/* service/rag-core/data/raw/
     ```
   * **Processing Note:**
     Moving **all** manuals may require up to **90 minutes (1 hour and 30 minutes)** on resource-limited machines. For an initial quick test, it's recommended to move only **1 or 2 manuals**.
     All models are loaded at startup, so the system initialization may take a few minutes.

2. **Trigger the Ingestion Process:**

   * Once the files are in the folder, navigate to the Airflow web interface: `http://localhost:8080`
   * Log in with the credentials configured in the `.env` file
   * Find the DAG named **`rag_ingetion_pipeline_v2.py`** and trigger it manually
   * This process will connect with `rag-core` to initiate cleaning, chunking, and vector storage in **Qdrant**

### 4. Queries and Evaluation

1. **Access the Frontend:** Once the DAG processing is complete, access the chat interface: `http://localhost:8501`
2. **Submit Queries:** Use the chat to ask questions about the content of the processed manuals
3. **Reference Questions:** The **`questions.json`** file contains a set of questions formulated by an SCADA SDM expert. Use these questions as a reference to:
   * Verify expected answers
   * Execute **Deepeval** scripts for RAG and LLM quality evaluation

-----

## 📞 Contact

If you have questions, suggestions, or want to collaborate on the project, you can contact the main developer through:

* **Name:** Carlos Villarreal P.
* **Email:** `villarreal.fx@gmail.com`
* **LinkedIn:** [`linkedin.com/in/carlos-villarreal-paredes/`](https://www.linkedin.com/in/carlos-villarreal-paredes/)

-----

## 🔬 Usage Guide and Demonstration

For a visual demonstration and a step-by-step guide on how to use the application, from triggering the Airflow process to making queries in the frontend and performing RAG evaluation, consult our detailed tutorial:

➡️ **[COMPLETE USAGE AND VALIDATION TUTORIAL](TUTORIAL.md)**

In the tutorial you will find:
* Screenshots of the manual Airflow trigger
* Query examples using the questions from `preguntas.json`
* How feedback and context traceability are displayed in the user interface

---