// static/js/main.js
'use strict';

document.addEventListener('DOMContentLoaded', () => {
  console.log('main.js loaded');

  // ─── Tab Switching ───────────────────────────────────────────────────────
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(btn.dataset.tab).classList.add('active');
    });
  });

  // ─── Image Preview ───────────────────────────────────────────────────────
  const imageInput   = document.getElementById('image-input');
  const previewImage = document.getElementById('preview-image');
  const previewBox   = document.getElementById('preview-container');
  imageInput?.addEventListener('change', () => {
    const file = imageInput.files[0];
    if (!file) {
      previewImage.src = '';
      previewBox.classList.remove('has-image');
      return;
    }
    previewImage.src = URL.createObjectURL(file);
    previewBox.classList.add('has-image');
    confetti({ particleCount: 40, spread: 40, origin: { y: 0.6 } });
  });

  // ─── Camera Capture ──────────────────────────────────────────────────────
  window.openCamera = () => {
    const video = document.getElementById('camera');
    const captureBtn = document.getElementById('captureBtn');
    const mode = document.getElementById('cameraSelect').value;
    navigator.mediaDevices.getUserMedia({ video: { facingMode: { exact: mode } } })
      .then(stream => {
        video.style.display = 'block';
        video.srcObject = stream;
        captureBtn.style.display = 'inline-block';
      })
      .catch(() => alert('Camera access denied or unavailable!'));
  };

  window.captureImage = () => {
    const video  = document.getElementById('camera');
    const canvas = document.getElementById('canvas');
    const ctx    = canvas.getContext('2d');
    canvas.width  = video.videoWidth;
    canvas.height = video.videoHeight;
    ctx.drawImage(video, 0, 0);
    canvas.toBlob(blob => {
      const file = new File([blob], 'capture.jpg', { type: 'image/jpeg' });
      const dt   = new DataTransfer();
      dt.items.add(file);
      document.getElementById('capturedImage').files = dt.files;
      document.getElementById('cameraForm').submit();
    }, 'image/jpeg');
  };

  // ─── Fortune Spinner ─────────────────────────────────────────────────────
  const fortunes  = [
    '🍌 Tip: Keep bananas away from apples to slow ripening!',
    '🥝 Fact: Kiwis have more vitamin C than oranges!',
    '🍇 Challenge: Try a fruit you’ve never eaten this week!',
    '🍍 Tip: Pineapple helps with digestion!',
    '🍓 Fact: Strawberries are the only fruit with seeds on the outside!'
  ];
  const wheel     = document.getElementById('fruitWheel');
  const resultDiv = document.getElementById('spinResult');
  const spinBtn   = document.getElementById('spinBtn');
  function spinWheel() {
    wheel.style.transition = 'none';
    wheel.style.transform  = 'rotate(0deg)';
    requestAnimationFrame(() => {
      const rotation = 360 * 3 + Math.floor(Math.random() * 360);
      wheel.style.transition = 'transform 2s ease-out';
      wheel.style.transform  = `rotate(${rotation}deg)`;
      setTimeout(() => {
        resultDiv.innerHTML = `<h3>${fortunes[Math.floor(Math.random()*fortunes.length)]}</h3>`;
        confetti({ particleCount: 60, spread: 50, origin: { y: 0.6 } });
      }, 2000);
    });
  }
  spinBtn?.addEventListener('click', spinWheel);

  // ─── BerryBot Chat Widget ────────────────────────────────────────────────
  const toggle       = document.getElementById('berrybot-toggle');
  const panel        = document.getElementById('berrybot-panel');
  const msgContainer = document.getElementById('berrybot-messages');
  const inputField   = document.getElementById('berrybot-text');
  const sendBtn      = document.getElementById('berrybot-send');
  const voiceBtn     = document.getElementById('voice-btn');
  let typingEl;

  toggle?.addEventListener('click', () => {
    panel.classList.toggle('hidden');
    panel.classList.toggle('visible');
  });

  voiceBtn?.addEventListener('click', () => {
    panel.classList.remove('hidden');
    panel.classList.add('visible');
    if ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window) {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      const recognition = new SpeechRecognition();
      recognition.lang = 'en-US';
      recognition.interimResults = false;

      recognition.start();

      recognition.addEventListener('result', e => {
        const transcript = Array.from(e.results)
          .map(r => r[0].transcript)
          .join('')
          .trim();
        sendMessage(transcript);
      });
    } else {
      alert('Speech recognition not supported in this browser.');
    }
  });

  function appendTypingIndicator() {
    typingEl = document.createElement('div');
    typingEl.className = 'message bot';
    typingEl.innerHTML = `<div class="bubble">🍓 BerryBot is typing…</div>`;
    msgContainer.appendChild(typingEl);
    msgContainer.scrollTop = msgContainer.scrollHeight;
  }

  function removeTypingIndicator() {
    typingEl?.remove();
  }

  function appendMessage(who, text) {
    const msgEl = document.createElement('div');
    msgEl.className = `message ${who}`;
    msgEl.innerHTML = `<div class="bubble">${text}</div>`;
    msgContainer.appendChild(msgEl);
    msgContainer.scrollTop = msgContainer.scrollHeight;
  }

  async function sendMessage(text = null) {
    const prompt = text ?? inputField.value.trim();
    if (!prompt) return;

    appendMessage('user', prompt);
    if (!text) inputField.value = '';
    appendTypingIndicator();

    const res = await fetch('/api/berrybot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt })
    });

    const { reply } = await res.json();
    removeTypingIndicator();
    appendMessage('bot', reply);
  }

  sendBtn?.addEventListener('click', () => sendMessage());
  inputField?.addEventListener('keypress', e => {
    if (e.key === 'Enter') sendMessage();
  });
// ─── Hex-card Chart Toggle & Injection ───────────────────────────────────
const chartToggle = document.getElementById('chartToggle');
const chartPanel  = document.getElementById('produceChart');

chartToggle.addEventListener('click', () => {
  chartPanel.classList.toggle('revealed');
  confetti({ particleCount: 20, spread: 30, origin: { y: 0.6 } });
});
const produceList = [
  { name: 'Orange',      benefit: 'Rich in Vitamin C',                    color: '#FFA500', emoji: '🍊' },
  { name: 'Pomegranate', benefit: 'Boosts Blood Health',                  color: '#C62828', emoji: '🍎' },
  { name: 'Spinach',     benefit: 'Good for Overall Health',              color: '#2E7D32', emoji: '🥬' },
  { name: 'Pumpkin',     benefit: 'Aids Digestion & Gut Health',          color: '#F57C00', emoji: '🎃' },
  { name: 'Apple',       benefit: 'High in Fiber & Vitamin C',            color: '#D32F2F', emoji: '🍏' },
  { name: 'Blueberry',   benefit: 'Packed with Antioxidants',              color: '#303F9F', emoji: '🫐' },
  { name: 'Avocado',     benefit: 'Heart-Healthy Monounsaturated Fats',    color: '#4CAF50', emoji: '🥑' },
  { name: 'Tomato',      benefit: 'Rich in Lycopene & Vitamins A, C',      color: '#E53935', emoji: '🍅' },
  { name: 'Carrot',      benefit: 'Supports Eye Health with Beta-Carotene',color: '#FB8C00', emoji: '🥕' },
  { name: 'Broccoli',    benefit: 'High in Fiber & Vitamins K, C',         color: '#388E3C', emoji: '🥦' },
  { name: 'Kiwi',        benefit: 'Vitamin C Powerhouse & Dietary Fiber',  color: '#7CB342', emoji: '🥝' },
  { name: 'Strawberry',  benefit: 'Antioxidant-Rich & Vitamin C Boost',     color: '#E91E63', emoji: '🍓' },
  { name: 'Mango',       benefit: 'Rich in Vitamins A & C',                color: '#FFB300', emoji: '🥭' },
  { name: 'Cucumber',    benefit: 'Hydrating & Low-Calorie Snack',         color: '#81C784', emoji: '🥒' },
  { name: 'Pineapple',   benefit: 'Aids Digestion with Bromelain',         color: '#FF9800', emoji: '🍍' },
  { name: 'Banana',      benefit: 'Great Source of Potassium',             color: '#FDD835', emoji: '🍌' },
  { name: 'Watermelon',  benefit: 'Hydrating & Rich in Vitamins A, C',     color: '#FF5252', emoji: '🍉' }
];
if (chartPanel) {
  chartPanel.innerHTML = '';
  produceList.forEach(item => {
    const wrap = document.createElement('div');
    wrap.className = 'hex-card';
    wrap.style.setProperty('--color', item.color);

    const inner = document.createElement('div');
    inner.className = 'hex-card-inner';

    inner.innerHTML = `
      <div class="hex-card-front">
        <div class="emoji">${item.emoji}</div>
        <div class="name">${item.name}</div>
      </div>
      <div class="hex-card-back">${item.benefit}</div>
    `;

    wrap.appendChild(inner);
    chartPanel.appendChild(wrap);
  });
}
});