const http = require("http");
const fs = require("fs");
const path = require("path");

// Collection definition
const collectionDef = `$kind: collection
name: Personal AI Assistant API
description: Test collection for FastAPI RAG (Retrieval-Augmented Generation) API with endpoints for PDF ingestion and query processing.
variables:
  - key: baseUrl
    value: ''
    description: Base URL of the API server (set via environment)
`;

// Ingest Valid PDF request
const ingestValidPDF = `$kind: http-request
name: Ingest Valid PDF
method: POST
url: '{{baseUrl}}/api/ingest'
order: 1000
body:
  type: formdata
  content:
    - key: file
      type: file
      src: ''
scripts:
  - type: afterResponse
    language: text/javascript
    code: |-
      pm.test("Status code is 200", function () {
          pm.response.to.have.status(200);
      });
      pm.test("Response has status success", function () {
          const json = pm.response.json();
          pm.expect(json.status).to.eql("success");
      });
      pm.test("Response contains filename", function () {
          const json = pm.response.json();
          pm.expect(json).to.have.property("filename");
          pm.expect(json.filename).to.be.a("string").and.not.empty;
      });
      pm.test("Response time is less than 5000ms", function () {
          pm.expect(pm.response.responseTime).to.be.below(5000);
      });
`;

// Ingest Non-PDF File request
const ingestNonPDF = `$kind: http-request
name: 'Ingest Non-PDF File (Should Fail)'
method: POST
url: '{{baseUrl}}/api/ingest'
order: 2000
body:
  type: formdata
  content:
    - key: file
      type: text
      value: not-a-pdf.txt
scripts:
  - type: afterResponse
    language: text/javascript
    code: |-
      pm.test("Status code is 4xx for invalid file type", function () {
          pm.expect(pm.response.code).to.be.within(400, 499);
      });
`;

// Ingest Without File request
const ingestNoFile = `$kind: http-request
name: 'Ingest Without File (Should Fail)'
method: POST
url: '{{baseUrl}}/api/ingest'
order: 3000
scripts:
  - type: afterResponse
    language: text/javascript
    code: |-
      pm.test("Status code is 422 for missing file", function () {
          pm.response.to.have.status(422);
      });
      pm.test("Response contains validation error detail", function () {
          const json = pm.response.json();
          pm.expect(json).to.have.property("detail");
      });
`;

// Query Valid Question request
const queryValid = `$kind: http-request
name: Query with Valid Question
method: POST
url: '{{baseUrl}}/api/query'
order: 1000
headers:
  - key: Content-Type
    value: application/json
body:
  type: json
  content: |-
    {
      "query": "What is RAG?"
    }
scripts:
  - type: afterResponse
    language: text/javascript
    code: |-
      pm.test("Status code is 200", function () {
          pm.response.to.have.status(200);
      });
      pm.test("Response has context array", function () {
          const json = pm.response.json();
          pm.expect(json).to.have.property("context");
          pm.expect(json.context).to.be.an("array");
      });
      pm.test("Response time is less than 10000ms", function () {
          pm.expect(pm.response.responseTime).to.be.below(10000);
      });
`;

// Query Empty String request
const queryEmpty = `$kind: http-request
name: 'Query with Empty String (Should Fail)'
method: POST
url: '{{baseUrl}}/api/query'
order: 2000
headers:
  - key: Content-Type
    value: application/json
body:
  type: json
  content: |-
    {
      "query": ""
    }
scripts:
  - type: afterResponse
    language: text/javascript
    code: |-
      pm.test("Status code is 422 for empty query", function () {
          pm.response.to.have.status(422);
      });
`;

// Query Without Body request
const queryNoBody = `$kind: http-request
name: 'Query Without Body (Should Fail)'
method: POST
url: '{{baseUrl}}/api/query'
order: 3000
headers:
  - key: Content-Type
    value: application/json
scripts:
  - type: afterResponse
    language: text/javascript
    code: |-
      pm.test("Status code is 422 for missing body", function () {
          pm.response.to.have.status(422);
      });
      pm.test("Response contains validation error detail", function () {
          const json = pm.response.json();
          pm.expect(json).to.have.property("detail");
      });
`;

// Query Long Input request
const queryLong = `$kind: http-request
name: Query with Long Input
method: POST
url: '{{baseUrl}}/api/query'
order: 4000
headers:
  - key: Content-Type
    value: application/json
body:
  type: json
  content: |-
    {
      "query": "Can you explain in detail the entire process of Retrieval-Augmented Generation, including how documents are chunked, embedded, stored in a vector database, retrieved via similarity search, and then used as context for a large language model to generate a final answer?"
    }
scripts:
  - type: afterResponse
    language: text/javascript
    code: |-
      pm.test("Status code is 200 for long query", function () {
          pm.response.to.have.status(200);
      });
      pm.test("Response has context array", function () {
          const json = pm.response.json();
          pm.expect(json).to.have.property("context");
          pm.expect(json.context).to.be.an("array");
      });
`;

// Development environment
const devEnv = `name: Development
values:
  - key: baseUrl
    value: 'http://localhost:8000'
    enabled: true
    type: default
`;

// Production environment
const prodEnv = `name: Production
values:
  - key: baseUrl
    value: 'https://your-production-url.com'
    enabled: true
    type: default
`;

const base = "C:/Users/Agustin/Desktop/Agustin/personal-ai-assistant";

const files = [
  [`${base}/postman/collections/Personal AI Assistant API/.resources/definition.yaml`, collectionDef],
  [`${base}/postman/collections/Personal AI Assistant API/Ingest PDF/Ingest Valid PDF.request.yaml`, ingestValidPDF],
  [`${base}/postman/collections/Personal AI Assistant API/Ingest PDF/Ingest Non-PDF File (Should Fail).request.yaml`, ingestNonPDF],
  [`${base}/postman/collections/Personal AI Assistant API/Ingest PDF/Ingest Without File (Should Fail).request.yaml`, ingestNoFile],
  [`${base}/postman/collections/Personal AI Assistant API/Query RAG/Query with Valid Question.request.yaml`, queryValid],
  [`${base}/postman/collections/Personal AI Assistant API/Query RAG/Query with Empty String (Should Fail).request.yaml`, queryEmpty],
  [`${base}/postman/collections/Personal AI Assistant API/Query RAG/Query Without Body (Should Fail).request.yaml`, queryNoBody],
  [`${base}/postman/collections/Personal AI Assistant API/Query RAG/Query with Long Input.request.yaml`, queryLong],
  [`${base}/postman/environments/Development.yaml`, devEnv],
  [`${base}/postman/environments/Production.yaml`, prodEnv],
];

let results = [];
for (const [filePath, content] of files) {
  try {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content, "utf8");
    results.push({ file: filePath, status: "OK" });
  } catch (e) {
    results.push({ file: filePath, status: "ERROR", error: e.message });
  }
}

const server = http.createServer((req, res) => {
  // @endpoint GET /status
  if (req.method === "GET" && req.url === "/status") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ results }));
  } else {
    res.writeHead(404);
    res.end("Not found");
  }
});

server.listen(process.env.PORT || 3000, () => {
  console.log("Files written:", JSON.stringify(results, null, 2));
});
