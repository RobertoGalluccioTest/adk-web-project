async function runAgent() {
    const params = document.getElementById("params").files[0];
    const pdf = document.getElementById("pdf").files[0];
    const key = document.getElementById("key").value || "";

    const out = document.getElementById("output");
    out.textContent = "Running...";

    if (!params || !pdf) {
        out.textContent = "Please select both files.";
        return;
    }

    const form = new FormData();
    form.append("params_file", params);
    form.append("pdf_file", pdf);
    form.append("key", key);

    try {
        const resp = await fetch("/run-agent", { method: "POST", body: form });
        const data = await resp.json();
        out.textContent = JSON.stringify(data, null, 2);
    } catch (e) {
        out.textContent = "Error: " + e.message;
    }
}

document.getElementById("run").addEventListener("click", runAgent);