import React from "react";
import { marked } from "marked";
import ProductCard from "./cards/ProductCard";
import CompatibilityCard from "./cards/CompatibilityCard";
import InstallGuide from "./cards/InstallGuide";
import RepairHelp from "./cards/RepairHelp";
import OrderCard from "./cards/OrderCard";
import CartCard from "./cards/CartCard";
import SuggestedPrompts from "./SuggestedPrompts";

marked.setOptions({ breaks: true });
const renderer = new marked.Renderer();
const origLink = renderer.link.bind(renderer);
renderer.link = function (href, title, text) {
  const html = origLink(href, title, text);
  return html.replace("<a ", '<a target="_blank" rel="noreferrer" ');
};
marked.use({ renderer });

function renderCard(card, i, ctx) {
  switch (card.type) {
    case "product":
      return <ProductCard key={i} card={card} {...ctx} />;
    case "compatibility":
      return <CompatibilityCard key={i} card={card} {...ctx} />;
    case "install":
      return <InstallGuide key={i} card={card} />;
    case "repair":
      return <RepairHelp key={i} card={card} {...ctx} />;
    case "order":
      return <OrderCard key={i} card={card} />;
    case "cart":
      return <CartCard key={i} card={card} />;
    default:
      return null;
  }
}

function Message({ message, onSuggestion, onPinModel, pinnedModel }) {
  const { role, content, cards = [], suggestions = [], streaming } = message;
  const isUser = role === "user";

  const ctx = { onSuggestion, onPinModel, pinnedModel };

  const html = content ? marked.parse(content) : "";

  return (
    <div className={`msg-row ${role}`}>
      {!isUser && <div className="speaker">PartSelect Assistant</div>}
      {(content || streaming) && (
        <div className={`bubble ${role}`}>
          <div dangerouslySetInnerHTML={{ __html: html }} />
          {streaming && !content && <span className="caret" />}
          {streaming && content && <span className="caret" />}
        </div>
      )}

      {cards.length > 0 && (
        <div className="cards">{cards.map((c, i) => renderCard(c, i, ctx))}</div>
      )}

      {!streaming && suggestions.length > 0 && (
        <SuggestedPrompts prompts={suggestions} onPick={onSuggestion} compact />
      )}
    </div>
  );
}

export default Message;
