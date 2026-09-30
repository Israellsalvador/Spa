// Fonte Serena — pequenos comportamentos da interface
(function () {
  // Copiar o Pix Copia e Cola
  document.querySelectorAll('[data-copiar]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var alvo = document.querySelector(btn.getAttribute('data-copiar'));
      if (!alvo) return;
      var original = btn.innerHTML;
      function ok() {
        btn.textContent = 'Copiado!';
        setTimeout(function () { btn.innerHTML = original; }, 2000);
      }
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(alvo.value).then(ok, function () { alvo.select(); document.execCommand('copy'); ok(); });
      } else {
        alvo.select(); document.execCommand('copy'); ok();
      }
    });
  });

  // Contagem regressiva do bloqueio do horário
  document.querySelectorAll('[data-prazo]').forEach(function (el) {
    var prazo = new Date(el.getAttribute('data-prazo')).getTime();
    if (isNaN(prazo)) return;
    function tick() {
      var resto = Math.max(0, Math.floor((prazo - Date.now()) / 1000));
      var m = Math.floor(resto / 60), s = resto % 60;
      el.textContent = m + ':' + (s < 10 ? '0' : '') + s;
      if (resto <= 0) { clearInterval(t); setTimeout(function () { location.reload(); }, 1500); }
    }
    var t = setInterval(tick, 1000);
    tick();
  });

  // Limite de opções no questionário
  document.querySelectorAll('form[data-limite]').forEach(function (form) {
    var limite = parseInt(form.getAttribute('data-limite'), 10);
    if (!(limite > 1)) return;
    var caixas = form.querySelectorAll('input[type=checkbox]');
    function atualizar() {
      var marcadas = form.querySelectorAll('input[type=checkbox]:checked').length;
      caixas.forEach(function (c) { c.disabled = !c.checked && marcadas >= limite; c.closest('.opcao').style.opacity = c.disabled ? .5 : 1; });
    }
    caixas.forEach(function (c) { c.addEventListener('change', atualizar); });
    atualizar();
  });

  // Confirmação antes de ações irreversíveis
  document.querySelectorAll('form[data-confirmar]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (!confirm(form.getAttribute('data-confirmar'))) e.preventDefault();
    });
  });

  // Barra fixa do celular: aparece depois que a pessoa rola a primeira dobra
  var barra = document.querySelector('[data-barra]');
  if (barra && document.body.classList.contains('tem-barra')) {
    var mostrar = function () { barra.classList.toggle('visivel', window.scrollY > window.innerHeight * 0.6); };
    window.addEventListener('scroll', mostrar, { passive: true });
    mostrar();
  }

  var reduzir = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Cabeçalho: transparente sobre a capa, sólido depois de rolar
  if (document.body.classList.contains('sobre-capa')) {
    var topo = function () { document.body.classList.toggle('rolou', window.scrollY > 40); };
    window.addEventListener('scroll', topo, { passive: true });
    topo();
  }

  // Revelar ao rolar
  var revelar = document.querySelectorAll('[data-revelar]');
  if ('IntersectionObserver' in window && !reduzir) {
    var io = new IntersectionObserver(function (entradas) {
      entradas.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('visto'); io.unobserve(e.target); }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.12 });
    revelar.forEach(function (el) { io.observe(el); });
  } else {
    revelar.forEach(function (el) { el.classList.add('visto'); });
  }

  // Ritual: troca a imagem fixa conforme a etapa em foco
  var etapas = document.querySelectorAll('[data-ritual-etapa]');
  var fotos = document.querySelectorAll('[data-ritual-foto]');
  var contador = document.querySelector('[data-ritual-contador]');
  if (etapas.length && fotos.length && 'IntersectionObserver' in window) {
    var ativar = function (i) {
      etapas.forEach(function (el, k) { el.classList.toggle('ativa', k === i); });
      fotos.forEach(function (el, k) { el.classList.toggle('ativa', k === i); });
      if (contador) contador.textContent = etapas[i].getAttribute('data-numero') + ' — IV';
    };
    var ioR = new IntersectionObserver(function (entradas) {
      entradas.forEach(function (e) {
        if (e.isIntersecting) ativar(parseInt(e.target.getAttribute('data-ritual-etapa'), 10));
      });
    }, { rootMargin: '-45% 0px -45% 0px' });
    etapas.forEach(function (el) { ioR.observe(el); });
  }

  // Filtro de categorias do cardápio (home)
  var filtro = document.querySelector('[data-filtro]');
  var alvo = document.querySelector('[data-filtro-alvo]');
  if (filtro && alvo) {
    filtro.addEventListener('click', function (ev) {
      var b = ev.target.closest('button[data-cat]');
      if (!b) return;
      var cat = b.getAttribute('data-cat');
      filtro.querySelectorAll('button').forEach(function (x) { x.setAttribute('aria-selected', x === b ? 'true' : 'false'); });
      alvo.querySelectorAll('.exp').forEach(function (c) {
        c.hidden = !!cat && c.getAttribute('data-cat') !== cat;
        if (!c.hidden) c.classList.add('visto');
      });
    });
  }

  // Fechar menus <details> ao clicar fora
  document.addEventListener('click', function (e) {
    document.querySelectorAll('details.conta-menu[open], details.menu-mobile[open]').forEach(function (d) {
      if (!d.contains(e.target)) d.removeAttribute('open');
    });
  });
})();
