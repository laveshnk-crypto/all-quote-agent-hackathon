import { useCallback, useEffect, useRef, useState } from 'react';

import './QuoteCarousel.css';

const money = (value, opts = {}) =>
  typeof value === 'number'
    ? new Intl.NumberFormat('en-CA', {
        style: 'currency',
        currency: 'CAD',
        maximumFractionDigits: 0,
        ...opts,
      }).format(value)
    : '—';

function QuoteCard({ quote, isCheapest, apiBase }) {
  const available = quote.status === 'SUCCESS' && quote.annual_premium;
  const monthly =
    typeof quote.annual_premium === 'number' ? Math.round(quote.annual_premium / 12) : null;

  return (
    <article
      className={`qc-card ${available ? '' : 'qc-card--empty'} ${
        isCheapest ? 'qc-card--best' : ''
      }`}
    >
      <header className="qc-card__head">
        <div>
          <h3>{quote.channel_name}</h3>
          <span className="qc-card__cat">{quote.channel_category}</span>
        </div>
        {isCheapest && <span className="qc-badge">Best rate</span>}
      </header>

      {available ? (
        <>
          <div className="qc-card__amount">
            <strong>{money(quote.annual_premium)}</strong>
            <span>per year</span>
            {monthly !== null && <em>about {money(monthly)}/month</em>}
          </div>

          {quote.headline && <p className="qc-card__headline">{quote.headline}</p>}
          {quote.matched_on && (
            <p className="qc-card__matched">
              <span>Matched on</span> {quote.matched_on}
            </p>
          )}

          {quote.comparisons?.length > 0 && (
            <ul className="qc-card__comparisons">
              {quote.comparisons.map((c, i) => (
                <li key={`${c.label}-${i}`}>
                  <span className="qc-comp__label">{c.label}</span>
                  <span className="qc-comp__value">{money(c.annual)}</span>
                  {c.note && <span className="qc-comp__note">{c.note}</span>}
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <div className="qc-card__unavailable">
          <span className="qc-card__dash">—</span>
          <p className="qc-card__reason">
            This source {quote.unavailable_reason || 'returned no rate'}.
          </p>
          {quote.headline && <p className="qc-card__detail">{quote.headline}</p>}
        </div>
      )}

      <div className="qc-card__links">
        {quote.screenshot_url && (
          <a
            className="qc-card__link"
            href={`${apiBase}${quote.screenshot_url}`}
            target="_blank"
            rel="noreferrer noopener"
          >
            Screenshot proof
          </a>
        )}
        {quote.source_url && (
          <a
            className="qc-card__link"
            href={quote.source_url}
            target="_blank"
            rel="noreferrer noopener"
          >
            View source
          </a>
        )}
      </div>
    </article>
  );
}

export default function QuoteCarousel({ summary, quotes, apiBase, onCompare }) {
  const trackRef = useRef(null);
  const [active, setActive] = useState(0);

  // Derive the active card from scroll position so native swipe, the arrows and
  // the dots all stay in sync without fighting each other.
  const handleScroll = useCallback(() => {
    const track = trackRef.current;
    if (!track) return;
    const index = Math.round(track.scrollLeft / track.clientWidth);
    setActive((prev) => (prev === index ? prev : index));
  }, []);

  const goTo = useCallback((index) => {
    const track = trackRef.current;
    if (!track) return;
    const clamped = Math.max(0, Math.min(index, track.children.length - 1));
    track.scrollTo({ left: clamped * track.clientWidth, behavior: 'smooth' });
  }, []);

  useEffect(() => {
    const onKey = (event) => {
      if (event.key === 'ArrowRight') goTo(active + 1);
      if (event.key === 'ArrowLeft') goTo(active - 1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [active, goTo]);

  const cheapestName = summary?.cheapest_channel;

  return (
    <div className="qc">
      <header className="qc__summary">
        <span className="qc__eyebrow">
          {summary?.channels_with_a_price ?? 0} of {summary?.channels_run ?? 0} sources returned a
          rate
        </span>
        <h2>
          {summary?.cheapest_annual ? money(summary.cheapest_annual) : '—'}
          <small> cheapest / year</small>
        </h2>
        {summary?.spread_annual ? (
          <p className="qc__spread">
            {money(summary.spread_annual)} between the cheapest and priciest source
          </p>
        ) : null}
      </header>

      <div className="qc__viewport">
        <button
          type="button"
          className="qc__arrow qc__arrow--prev"
          onClick={() => goTo(active - 1)}
          disabled={active === 0}
          aria-label="Previous source"
        >
          ‹
        </button>

        <div className="qc__track" ref={trackRef} onScroll={handleScroll}>
          {quotes.map((quote) => (
            <div className="qc__slide" key={quote.channel_id}>
              <QuoteCard
                quote={quote}
                isCheapest={quote.is_recommended ?? quote.channel_name === cheapestName}
                apiBase={apiBase}
              />
            </div>
          ))}
        </div>

        <button
          type="button"
          className="qc__arrow qc__arrow--next"
          onClick={() => goTo(active + 1)}
          disabled={active >= quotes.length - 1}
          aria-label="Next source"
        >
          ›
        </button>
      </div>

      <nav className="qc__dots" aria-label="Choose a source">
        {quotes.map((quote, index) => (
          <button
            key={quote.channel_id}
            type="button"
            className={`qc__dot ${index === active ? 'is-active' : ''} ${
              quote.status === 'SUCCESS' ? '' : 'is-empty'
            }`}
            onClick={() => goTo(index)}
            aria-label={quote.channel_name}
            aria-current={index === active}
          />
        ))}
      </nav>

      <div className="qc__actions">
        <p className="qc__hint">Swipe or use ← → to browse sources</p>
        <button type="button" className="qc__compare" onClick={onCompare}>
          Compare all in a table
        </button>
      </div>
    </div>
  );
}
