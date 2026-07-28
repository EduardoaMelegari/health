const App = {
  async post(url, body) {
    let res;
    try {
      res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch {
      App.toast("Sem conexão com o servidor.");
      throw new Error("Sem conexão com o servidor.");
    }
    if (!res.ok) {
      // as rotas devolvem {error: "..."} — mostra a mensagem real, não um genérico
      let msg = "Falha na requisição.";
      try { msg = (await res.json()).error || msg; } catch {}
      App.toast(msg);
      throw new Error(msg);
    }
    return res.json();
  },

  _toastTimer: null,
  toast(msg) {
    let t = document.getElementById("toast");
    if (!t) {
      t = document.createElement("div");
      t.id = "toast";
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(App._toastTimer);
    App._toastTimer = setTimeout(() => t.classList.remove("show"), 4000);
  },

  fmt(n) {
    return Math.round(n).toLocaleString("pt-BR");
  },

  toggleTheme() {
    const root = document.documentElement;
    const current = root.dataset.theme
      || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    localStorage.setItem("theme", next);
  },

  async toggleTask(el, templateId, date) {
    el.classList.toggle("done");
    try {
      const r = await this.post("/api/task/toggle", { template_id: templateId, date });
      el.classList.toggle("done", r.done);
    } catch {
      el.classList.toggle("done");
    }
  },

  // cabeçalho da Hoje: donut de kcal restantes + linha mono dos macros
  updateMacros(consumed, targets) {
    const ring = document.getElementById("kcal-ring");
    if (ring) {
      const pct = targets.kcal ? (100 * consumed.kcal) / targets.kcal : 0;
      ring.style.setProperty("--pct", Math.min(100, pct).toFixed(1) + "%");
      ring.classList.toggle("over", pct > 107);
      document.getElementById("kcal-left").textContent =
        this.fmt(Math.max(0, targets.kcal - consumed.kcal));
    }
    const line = document.getElementById("macro-line");
    if (line) {
      const p = (k) => `${this.fmt(consumed[k])}/${this.fmt(targets[k])}`;
      line.textContent = `P ${p("protein_g")} · C ${p("carbs_g")} · G ${p("fat_g")}`;
    }
  },
};
