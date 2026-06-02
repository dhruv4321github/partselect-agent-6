import React from "react";
import "./cards.css";

function PlaceholderIcon() {
  return (
    <svg className="ph" width="40" height="40" viewBox="0 0 24 24" fill="none">
      <path
        d="M4 7.5 12 3l8 4.5v9L12 21l-8-4.5v-9Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <path d="m8 9.8 4 2.2 4-2.2" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

function ProductCard({ card, onSuggestion }) {
  const {
    name,
    brand,
    appliance_type,
    ps_number,
    mfr_number,
    price,
    in_stock,
    rating,
    review_count,
    image_url,
    url,
    description,
    symptoms_fixed = [],
  } = card;

  const ask = (q) => onSuggestion && onSuggestion(q);

  return (
    <div className="card product">
      <div className="product-img">
        {image_url ? <img src={image_url} alt={name} onError={(e) => (e.target.style.display = "none")} /> : <PlaceholderIcon />}
      </div>
      <div className="product-body">
        <div className="product-name">{name}</div>
        <div className="product-meta">
          <span className="ps">{ps_number}</span>
          {mfr_number && <span>Mfr #{mfr_number}</span>}
          <span>
            {brand} · {appliance_type}
          </span>
        </div>

        <div className="product-row">
          <span className="price">${Number(price).toFixed(2)}</span>
          <div style={{ display: "flex", gap: 6 }}>
            {rating ? (
              <span className="pill rating">
                ★ {rating} {review_count ? `(${review_count})` : ""}
              </span>
            ) : null}
            <span className={`pill ${in_stock ? "stock-in" : "stock-out"}`}>
              {in_stock ? "In stock" : "Out of stock"}
            </span>
          </div>
        </div>

        {description && (
          <div className="product-desc">{description}</div>
        )}

        {symptoms_fixed.length > 0 && (
          <div className="product-tags">
            {symptoms_fixed.slice(0, 3).map((s, i) => (
              <span key={i} className="pill symptom">
                {s}
              </span>
            ))}
          </div>
        )}

        <div className="btn-row">
          <button className="btn btn-primary" onClick={() => ask(`Add ${ps_number} to my cart`)}>
            Add to cart
          </button>
          <button className="btn btn-ghost" onClick={() => ask(`How do I install ${ps_number}?`)}>
            Install guide
          </button>
          {url && (
            <a className="btn btn-ghost" href={url} target="_blank" rel="noreferrer">
              View on PartSelect
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

export default ProductCard;
