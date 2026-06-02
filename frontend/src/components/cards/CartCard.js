import React from "react";
import "./cards.css";

function CartCard({ card }) {
  const { items = [], item_count = 0, total = 0 } = card;

  if (!items.length) {
    return (
      <div className="card cart">
        <span className="cart-check">✓</span>
        <div className="cart-info">
          <div className="cart-title">Cart is empty</div>
        </div>
      </div>
    );
  }

  return (
    <div className="card cart-card">
      <div className="card-head">
        <div className="card-head-icon" style={{ background: "var(--ok)" }}>🛒</div>
        <div>
          <div className="card-head-title">Your Cart</div>
          <div className="card-head-sub">{item_count} item{item_count !== 1 ? "s" : ""}</div>
        </div>
      </div>
      <div className="card-content">
        <div className="cart-items">
          {items.map((item, i) => (
            <div className="cart-item" key={item.ps_number || i}>
              <div className="cart-item-info">
                <span className="cart-item-name">{item.name}</span>
                <span className="cart-item-meta">{item.ps_number}</span>
              </div>
              <div className="cart-item-right">
                <span className="cart-item-qty">×{item.quantity}</span>
                <span className="cart-item-price">${Number(item.line_total).toFixed(2)}</span>
              </div>
            </div>
          ))}
        </div>
        <div className="cart-footer">
          <span className="cart-footer-label">Total</span>
          <span className="cart-footer-total">${Number(total).toFixed(2)}</span>
        </div>
      </div>
    </div>
  );
}

export default CartCard;
