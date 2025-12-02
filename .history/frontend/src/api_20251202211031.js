const API_BASE = "http://localhost:8000";

export async function uploadFile(file, onProgress) {
  const formData = new FormData();
  formData.append("file", file);

  return fetch(`${API_BASE}/api/upload`, {
    method: "POST",
    body: formData,
  }).then(async (res) => {
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  });
}

export async function askQuestion(query, mode = "auto", onChunk) {
  const response = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, mode }),
  });
  return response.json();
}

export async function health() {
  const res = await fetch(`${API_BASE}/health`);
  return res.json();
}
