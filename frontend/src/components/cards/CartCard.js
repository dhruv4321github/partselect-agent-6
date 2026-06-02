import React from "react";
import "./cards.css";

function CartCard({ card }) {
  const { quantity, line_total, cart_url, part } = card;
  const name = part?.name || "Item";

  return (
    <div className="card cart">
      <span className="cart-check">✓</span>
      <div className="cart-info">
        <div className="cart-title">Added to cart</div>
        <div className="cart-sub">
          {quantity} × {name}
          {part?.ps_number ? ` · ${part.ps_number}` : ""}
        </div>
      </div>
      {line_total != null && <span className="cart-total">${Number(line_total).toFixed(2)}</span>}
      {cart_url && (
        <a className="btn btn-primary" href={cart_url} target="_blank" rel="noreferrer">
          View cart
        </a>
      )}
    </div>
  );
}

export default CartCard;
