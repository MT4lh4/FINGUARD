// FinGuard AI - Background Script

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "analyze_impulse") {
        
        // FastAPI sunucusuna istek at
        fetch("http://127.0.0.1:8000/analyze-product", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(request.product)
        })
        .then(response => response.json())
        .then(data => {
            // Sonucu content.js'e geri gönder
            chrome.tabs.sendMessage(sender.tab.id, {
                action: "show_decision",
                data: data
            });
        })
        .catch(error => {
            console.error("FinGuard API Hatası:", error);
            chrome.tabs.sendMessage(sender.tab.id, {
                action: "show_error",
                error: error.message
            });
        });
        
        return true; // Asenkron yanıt için
    }
});
