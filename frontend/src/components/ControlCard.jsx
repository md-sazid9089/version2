import React from 'react';
import styled from 'styled-components';

const ControlCard = ({ IconComponent, title, description, accent }) => {
  return (
    <StyledWrapper>
      <div className="card">
        <div className="card__border" />
        <div className="card_header">
          <div className="card_icon" style={{ color: accent }}>
            <IconComponent size={24} strokeWidth={2} />
          </div>
          <h3 className="card_title">{title}</h3>
        </div>
        <p className="card_description">{description}</p>
        <div className="card_footer">
          <span className="arrow">→</span>
        </div>
      </div>
    </StyledWrapper>
  );
};

const StyledWrapper = styled.div`
  .card {
    --white: hsl(0, 0%, 100%);
    --black: hsl(240, 15%, 9%);
    --paragraph: hsl(0, 0%, 83%);
    --line: hsl(240, 9%, 17%);
    --primary: hsl(266, 92%, 58%);

    position: relative;
    display: flex;
    flex-direction: column;
    gap: 1.2rem;
    padding: 1.5rem;
    width: 100%;
    min-height: 280px;
    background-color: hsla(240, 15%, 9%, 1);
    background-image: radial-gradient(
        at 88% 40%,
        hsla(240, 15%, 9%, 1) 0px,
        transparent 85%
      ),
      radial-gradient(at 49% 30%, hsla(240, 15%, 9%, 1) 0px, transparent 85%),
      radial-gradient(at 14% 26%, hsla(240, 15%, 9%, 1) 0px, transparent 85%),
      radial-gradient(at 0% 64%, hsla(263, 93%, 56%, 1) 0px, transparent 85%),
      radial-gradient(at 41% 94%, hsla(284, 100%, 84%, 1) 0px, transparent 85%),
      radial-gradient(at 100% 99%, hsla(306, 100%, 57%, 1) 0px, transparent 85%);

    border-radius: 1rem;
    box-shadow: 0px -16px 24px 0px rgba(255, 255, 255, 0.15) inset;
    overflow: hidden;
  }

  .card .card__border {
    overflow: hidden;
    pointer-events: none;
    position: absolute;
    z-index: -10;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: calc(100% + 2px);
    height: calc(100% + 2px);
    background-image: linear-gradient(
      0deg,
      hsl(0, 0%, 100%) -50%,
      hsl(0, 0%, 40%) 100%
    );
    border-radius: 1rem;
  }

  .card .card__border::before {
    content: "";
    pointer-events: none;
    position: absolute;
    z-index: 1;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) rotate(0deg);
    transform-origin: left;
    width: 200%;
    height: 10rem;
    background-image: linear-gradient(
      0deg,
      hsla(0, 0%, 100%, 0) 0%,
      hsl(277, 95%, 60%) 40%,
      hsl(277, 95%, 60%) 60%,
      hsla(0, 0%, 40%, 0) 100%
    );
    animation: rotate 6s linear infinite;
  }

  @keyframes rotate {
    to {
      transform: translate(-50%, -50%) rotate(360deg);
    }
  }

  .card .card_header {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    position: relative;
    z-index: 2;
  }

  .card .card_icon {
    font-size: 2rem;
    font-weight: 700;
    width: 44px;
    height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .card .card_title {
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--white);
    margin: 0;
    letter-spacing: -0.01em;
  }

  .card .card_description {
    font-size: 0.9rem;
    color: var(--paragraph);
    line-height: 1.6;
    margin: 0;
    position: relative;
    z-index: 2;
  }

  .card .card_footer {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: auto;
    position: relative;
    z-index: 2;
  }

  .card .arrow {
    font-size: 1.2rem;
    font-weight: 700;
    color: var(--primary);
  }

  @media (max-width: 1024px) {
    .card {
      padding: 1.2rem;
      min-height: 260px;
    }

    .card .card_title {
      font-size: 1rem;
    }

    .card .card_description {
      font-size: 0.85rem;
    }
  }

  @media (max-width: 640px) {
    .card {
      padding: 1rem;
      gap: 1rem;
      min-height: 240px;
    }

    .card .card_icon {
      width: 40px;
      height: 40px;
      font-size: 1.5rem;
    }

    .card .card_title {
      font-size: 0.95rem;
    }

    .card .card_description {
      font-size: 0.8rem;
    }
  }
`;

export default ControlCard;
