// FinGuard AI - Background Script

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "analyze_impulse") {

        fetch("http://127.0.0.1:8000/analyze-product", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(request.product)
        })
        .then(response => {
            if (!response.ok) throw new Error("HTTP " + response.status);
            return response.json();
        })
        .then(data => {
            // Backend'den gelen tüm veriyi (alternatives dahil) content.js'e ilet
            chrome.tabs.sendMessage(sender.tab.id, {
                action: "show_decision",
                data: {
                    decision:      data.decision      || "BEKLE",
                    message:       data.message       || data.intervention || "",
                    category:      data.category      || "",
                    budget_status: data.budget_status || {},
                    // Alternatif ürün linkleri — backend boş dönerse [] kullan
                    alternatives:  data.alternatives || []
                }
            });
        })
        .catch(error => {
            console.error("FinGuard API Hatası:", error);
            chrome.tabs.sendMessage(sender.tab.id, {
                action: "show_error",
                error: error.message
            });
        });

        return true;
    }
});
