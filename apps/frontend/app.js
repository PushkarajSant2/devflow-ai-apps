const paymentStatus = document.querySelector("#payment-status");
const orderStatus = document.querySelector("#order-status");
const output = document.querySelector("#output");

const orderApi = "http://localhost:8081";
const paymentApi = "http://localhost:8080";

function show(data) {
  output.textContent = JSON.stringify(data, null, 2);
}

function setStatus(element, ok, label) {
  element.textContent = label;
  element.classList.toggle("status-ok", ok);
  element.classList.toggle("status-bad", !ok);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const body = await response.json();
  return { ok: response.ok, status: response.status, body };
}

async function refreshStatus() {
  try {
    const payment = await fetchJson(`${paymentApi}/readyz`);
    setStatus(paymentStatus, payment.ok, payment.ok ? "ready" : payment.body.status || "not ready");
  } catch (error) {
    setStatus(paymentStatus, false, "offline");
  }

  try {
    const order = await fetchJson(`${orderApi}/readyz`);
    setStatus(orderStatus, order.ok, order.ok ? "ready" : order.body.status || "not ready");
  } catch (error) {
    setStatus(orderStatus, false, "offline");
  }
}

async function createOrder() {
  const payload = {
    customer_id: document.querySelector("#customer-id").value,
    items: [
      {
        sku: document.querySelector("#sku").value,
        quantity: Number(document.querySelector("#quantity").value),
        price: Number(document.querySelector("#price").value),
      },
    ],
  };

  const result = await fetchJson(`${orderApi}/api/orders`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  show(result);
  refreshStatus();
}

async function breakPayment() {
  const result = await fetchJson(`${paymentApi}/admin/break`, { method: "POST" });
  show(result);
  refreshStatus();
}

async function recoverPayment() {
  const result = await fetchJson(`${paymentApi}/admin/recover`, { method: "POST" });
  show(result);
  refreshStatus();
}

document.querySelector("#create-order").addEventListener("click", createOrder);
document.querySelector("#break-payment").addEventListener("click", breakPayment);
document.querySelector("#recover-payment").addEventListener("click", recoverPayment);
document.querySelector("#refresh-status").addEventListener("click", refreshStatus);

refreshStatus();
