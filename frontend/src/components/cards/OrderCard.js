import React from "react";
import "./cards.css";

function BoxIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none">
      <path
        d="M4 7.5 12 3l8 4.5v9L12 21l-8-4.5v-9Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="m4 7.5 8 4.5 8-4.5M12 12v9" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

function OrderCard({ card }) {
  const {
    order_id,
    status,
    placed_on,
    items = [],
    subtotal,
    shipping,
    total,
    tracking_url,
    estimated_delivery,
  } = card;

  const statusClass = (status || "").toLowerCase();

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-head-icon" style={{ background: "var(--ps-teal-dark)" }}>
          <BoxIcon />
        </span>
        <div>
          <div className="card-head-title">Order {order_id}</div>
          {placed_on && <div className="card-head-sub">Placed {placed_on}</div>}
        </div>
        <span className={`order-status ${statusClass}`}>{status}</span>
      </div>

      <div className="card-content">
        {items.length > 0 && (
          <div className="order-items">
            {items.map((it, i) => (
              <div className="order-item" key={i}>
                <span>
                  {it.name} <span className="qty">×{it.quantity}</span>
                </span>
                <span>${Number(it.price * it.quantity).toFixed(2)}</span>
              </div>
            ))}
          </div>
        )}

        <div className="order-totals">
          {subtotal != null && (
            <div className="row">
              <span>Subtotal</span>
              <span>${Number(subtotal).toFixed(2)}</span>
            </div>
          )}
          {shipping != null && (
            <div className="row">
              <span>Shipping</span>
              <span>{shipping === 0 ? "Free" : `$${Number(shipping).toFixed(2)}`}</span>
            </div>
          )}
          {total != null && (
            <div className="row total">
              <span>Total</span>
              <span>${Number(total).toFixed(2)}</span>
            </div>
          )}
        </div>

        {estimated_delivery && (
          <div className="tools-needed" style={{ marginTop: 10 }}>
            <b>Estimated delivery:</b> {estimated_delivery}
          </div>
        )}

        {tracking_url && (
          <div className="btn-row">
            <a className="btn btn-primary" href={tracking_url} target="_blank" rel="noreferrer">
              Track package
            </a>
          </div>
        )}
      </div>
    </div>
  );
}

export default OrderCard;
