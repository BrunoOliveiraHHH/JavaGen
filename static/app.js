// JavaGen — interações da página (carregar exemplo, preview, gerar+baixar, toast).

const form = document.getElementById("genForm");
const sqlText = document.getElementById("sqlText");

// Submit do formulário => gera e baixa o .zip via fetch (para mostrar o toast).
form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    gerar();
});

function nomeArquivo(input) {
    const label = document.getElementById("fileLabel");
    label.textContent = input.files.length ? input.files[0].name : "Ou enviar arquivo .sql…";
}

async function carregarExemplo() {
    try {
        const resp = await fetch("/sample");
        sqlText.value = await resp.text();
        toast("SQL de exemplo carregado.", "ok");
    } catch (e) {
        toast("Não foi possível carregar o exemplo.", "err");
    }
}

async function analisar() {
    const resp = await fetch("/preview", { method: "POST", body: new FormData(form) });
    const data = await resp.json().catch(() => ({ ok: false, error: "Resposta inválida." }));
    const box = document.getElementById("preview");
    const body = document.getElementById("previewBody");
    if (!data.ok) {
        toast(data.error || "Falha ao analisar.", "err");
        box.classList.add("hidden");
        return;
    }
    body.innerHTML = data.tables.map(renderTabela).join("");
    box.classList.remove("hidden");
    box.scrollIntoView({ behavior: "smooth" });
}

function renderTabela(t) {
    const cols = t.columns.map((c) => {
        let tags = "";
        if (c.pk) tags += '<span class="tag pk">PK</span>';
        if (c.fk) tags += `<span class="tag fk">FK → ${c.fk}</span>`;
        return `<tr><td>${c.name}${tags}</td><td>${c.type}</td><td>${c.java}</td></tr>`;
    }).join("");
    return `<h3>${t.name} <small>→ ${t.class}</small></h3>
        <table><thead><tr><th>Coluna</th><th>Tipo SQL</th><th>Tipo Java</th></tr></thead>
        <tbody>${cols}</tbody></table>`;
}

async function gerar() {
    const resp = await fetch("/generate", { method: "POST", body: new FormData(form) });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({ error: "Falha na geração." }));
        toast(data.error || "Falha na geração.", "err");
        return;
    }
    // Sucesso: baixa o blob e mostra o aviso na tela.
    const blob = await resp.blob();
    const nome = resp.headers.get("X-Gen-Filename") || "spring.zip";
    const tabelas = resp.headers.get("X-Gen-Tables") || "?";
    const arquivos = resp.headers.get("X-Gen-Files") || "?";
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = nome;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast(`Geração concluída! ${tabelas} tabela(s), ${arquivos} arquivo(s). Output limpo.`, "ok");
}

let toastTimer = null;
function toast(msg, tipo) {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.className = "toast " + (tipo === "err" ? "err" : "ok");
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.add("hidden"), 5000);
}
