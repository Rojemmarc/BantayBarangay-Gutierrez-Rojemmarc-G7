/* Standard interactive UX enhancements for BantayBarangay */
(function () {
  var d = document;
  var $ = function (sel, root) {
    return (root || d).querySelector(sel);
  };

  /* 1. Theme toggle */
  var tg = $('#themeToggle');
  if (tg) {
    var paintTheme = function () {
      var mode = d.documentElement.dataset.theme;
      tg.textContent = mode === 'dark' ? '☀' : '☾';
      tg.setAttribute('aria-label', mode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
    };
    paintTheme();
    tg.addEventListener('click', function () {
      var next = d.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      d.documentElement.dataset.theme = next;
      try {
        localStorage.setItem('theme', next);
      } catch (e) {}
      paintTheme();
    });
  }

  /* 2. Accessible confirmation modal + double-submit guard */
  var confirmModal = $('#confirmModal');
  var confirmMessage = $('#confirmMessage');
  var confirmProceed = $('#confirmProceed');
  var pendingForm = null;

  if (confirmModal && confirmProceed) {
    confirmProceed.addEventListener('click', function () {
      if (!pendingForm) return;
      var form = pendingForm;
      pendingForm = null;
      form.dataset.confirmed = '1';
      confirmModal.close();
      form.requestSubmit ? form.requestSubmit() : form.submit();
    });
    confirmModal.addEventListener('close', function () {
      pendingForm = null;
    });
  }

  d.addEventListener('submit', function (e) {
    var f = e.target;
    if (f.dataset.confirm && f.dataset.confirmed !== '1') {
      if (confirmModal && typeof confirmModal.showModal === 'function' && confirmMessage) {
        e.preventDefault();
        pendingForm = f;
        confirmMessage.textContent = f.dataset.confirm;
        confirmModal.showModal();
        return;
      }
      if (!window.confirm(f.dataset.confirm)) {
        e.preventDefault();
        return;
      }
    }
    if (f.dataset.nobusy !== undefined || f.method === 'get') return;
    if (f.dataset.busy) {
      e.preventDefault();
      return;
    }
    f.dataset.busy = '1';
    var btn = e.submitter || $('button:not([type=button])', f);
    if (btn) {
      setTimeout(function () {
        btn.dataset.label = btn.textContent;
        btn.disabled = true;
        btn.textContent = 'Please wait…';
      }, 0);
    }
  });

  window.addEventListener('pageshow', function (e) {
    if (e.persisted) {
      location.reload();
      return;
    }
    d.querySelectorAll('form[data-busy]').forEach(function (f) {
      delete f.dataset.busy;
      delete f.dataset.confirmed;
      f.querySelectorAll('button[disabled]').forEach(function (b) {
        b.disabled = false;
        if (b.dataset.label) b.textContent = b.dataset.label;
      });
    });
  });

  /* 3. Password show/hide toggles */
  d.querySelectorAll('[data-pw-toggle]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var input = d.getElementById(btn.dataset.pwToggle);
      if (!input) return;
      var showing = input.type === 'text';
      input.type = showing ? 'password' : 'text';
      btn.textContent = showing ? 'Show' : 'Hide';
      btn.setAttribute('aria-pressed', showing ? 'false' : 'true');
    });
  });

  /* 4. Live password strength hint */
  d.querySelectorAll('[data-pw-strength]').forEach(function (input) {
    var out = d.getElementById(input.dataset.pwStrength);
    if (!out) return;
    var update = function () {
      var v = input.value || '';
      if (!v) {
        out.textContent = 'Use at least 8 characters with letters, numbers, and symbols.';
        return;
      }
      var score = 0;
      if (v.length >= 8) score++;
      if (v.length >= 12) score++;
      if (/[A-Z]/.test(v) && /[a-z]/.test(v)) score++;
      if (/[0-9]/.test(v) && /[^A-Za-z0-9]/.test(v)) score++;
      var labels = ['Weak', 'Fair', 'Good', 'Strong', 'Very strong'];
      out.textContent = 'Password strength: ' + labels[score];
    };
    input.addEventListener('input', update);
  });

  /* 5. Live minimum character counter */
  d.querySelectorAll('[data-char-min]').forEach(function (field) {
    var min = parseInt(field.dataset.charMin, 10) || 0;
    var out = d.getElementById(field.dataset.charOut);
    if (!out) return;
    var update = function () {
      var len = field.value.trim().length;
      if (len >= min) {
        out.textContent = len + ' characters (meets minimum of ' + min + ')';
        out.classList.add('ok');
      } else {
        out.textContent = len + ' / ' + min + ' minimum characters';
        out.classList.remove('ok');
      }
    };
    update();
    field.addEventListener('input', update);
  });

  /* 6. Instant photo upload previews & client-side check */
  d.querySelectorAll('[data-photo-input]').forEach(function (input) {
    var previewEl = d.getElementById(input.dataset.photoPreview);
    var statusEl = d.getElementById(input.dataset.photoStatus);
    var maxFiles = parseInt(input.dataset.maxFiles || '3', 10);
    if (!previewEl) return;

    input.addEventListener('change', function () {
      previewEl.innerHTML = '';
      var files = Array.prototype.slice.call(input.files || []);
      var warnings = [];
      if (files.length > maxFiles) {
        warnings.push('You selected ' + files.length + ' photos; maximum allowed is ' + maxFiles + '.');
      }
      files.forEach(function (file) {
        var card = d.createElement('div');
        card.className = 'preview-item';
        var tooBig = file.size > 5 * 1024 * 1024;
        var badType = file.type !== 'image/jpeg' && file.type !== 'image/png';
        if (tooBig || badType) {
          card.classList.add('invalid');
          warnings.push(file.name + ': must be JPG or PNG up to 5 MB.');
        }
        var img = d.createElement('img');
        img.alt = file.name;
        img.src = URL.createObjectURL(file);
        img.onload = function () {
          URL.revokeObjectURL(img.src);
        };
        var meta = d.createElement('div');
        meta.className = 'meta';
        meta.textContent = file.name + ' (' + Math.max(1, Math.round(file.size / 1024)) + ' KB)';
        card.appendChild(img);
        card.appendChild(meta);
        previewEl.appendChild(card);
      });
      if (statusEl) {
        statusEl.textContent = warnings.length ? warnings.join(' ') : files.length ? files.length + ' photo(s) ready to upload.' : '';
        statusEl.className = warnings.length ? 'field-error' : 'field-hint';
      }
    });
  });

  /* 7. Photo lightbox modal */
  var lightbox = $('#photoLightbox');
  var lightboxImg = $('#lightboxImg');
  if (lightbox && lightboxImg) {
    d.addEventListener('click', function (e) {
      var img = e.target.closest('img[data-lightbox]');
      if (!img || typeof lightbox.showModal !== 'function') return;
      lightboxImg.src = img.src;
      lightboxImg.alt = img.alt || 'Report photo';
      lightbox.showModal();
    });
  }

  /* 8. Print report trigger */
  d.querySelectorAll('[data-print]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      window.print();
    });
  });

  /* 8b. Progressive scroll-reveal & smooth metric count-up */
  var reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var revealNodes = Array.prototype.slice.call(d.querySelectorAll('[data-reveal]'));
  if (!reducedMotion && revealNodes.length && 'IntersectionObserver' in window) {
    d.documentElement.classList.add('js-anim');
    revealNodes.forEach(function (el) {
      var idx = parseInt(el.dataset.stagger || '0', 10);
      if (idx > 0) el.style.setProperty('--reveal-delay', Math.min(idx * 65, 360) + 'ms');
    });
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.08, rootMargin: '0px 0px -24px 0px' }
    );
    revealNodes.forEach(function (el) {
      io.observe(el);
    });
  }

  if (!reducedMotion) {
    d.querySelectorAll('[data-count]').forEach(function (el) {
      var target = parseInt(el.dataset.count, 10);
      if (!Number.isFinite(target) || target <= 0) return;
      var duration = 650;
      var start = performance.now();
      var step = function (now) {
        var p = Math.min(1, (now - start) / duration);
        var eased = 1 - Math.pow(1 - p, 3);
        el.textContent = String(Math.round(target * eased));
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }

  /* 9. Leaflet maps (single-pin picker / detail view + Official multi-pin overview) */
  if (window.L) {
    d.querySelectorAll('[data-map]').forEach(function (el) {
      var lat = parseFloat(el.dataset.lat);
      var lng = parseFloat(el.dataset.lng);
      var pick = el.hasAttribute('data-pick');
      var la = $('#latitude');
      var lo = $('#longitude');
      var status = $('#mapStatus');
      var has = !pick || (la && la.value && lo && lo.value);

      if (pick && has) {
        lat = parseFloat(la.value);
        lng = parseFloat(lo.value);
        has = Number.isFinite(lat) && Number.isFinite(lng) && lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180;
        if (!has) {
          lat = parseFloat(el.dataset.lat);
          lng = parseFloat(el.dataset.lng);
        }
      }

      var map = L.map(el).setView([lat, lng], 15);
      var tiles = L.tileLayer('https://tile.openstreetmap.de/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
        maxZoom: 19,
      }).addTo(map);

      var marker = null;
      var putPin = function (ll) {
        if (marker) marker.setLatLng(ll);
        else marker = L.circleMarker(ll, { radius: 10, color: '#1E3A5F', fillColor: '#F4A825', fillOpacity: 1 }).addTo(map);
      };
      if (has) putPin([lat, lng]);

      tiles.on('tileerror', function () {
        if (status) status.textContent = 'Map tiles could not be loaded. Enter the latitude and longitude manually below.';
      });
      requestAnimationFrame(function () {
        map.invalidateSize();
      });
      window.addEventListener('resize', function () {
        map.invalidateSize();
      });

      if (pick && la && lo) {
        var pinText = $('#pinText');
        var setCoords = function (a, o) {
          la.value = a.toFixed(6);
          lo.value = o.toFixed(6);
          var ll = L.latLng(a, o);
          putPin(ll);
          map.setView(ll, Math.max(map.getZoom(), 16));
          if (pinText) pinText.textContent = 'Pinned: ' + la.value + ', ' + lo.value;
        };
        var syncInputs = function () {
          var a = parseFloat(la.value);
          var o = parseFloat(lo.value);
          if (la.value && lo.value && Number.isFinite(a) && Number.isFinite(o) && a >= -90 && a <= 90 && o >= -180 && o <= 180) {
            var ll = L.latLng(a, o);
            putPin(ll);
            map.setView(ll, Math.max(map.getZoom(), 15));
            if (pinText) pinText.textContent = 'Pinned: ' + a.toFixed(6) + ', ' + o.toFixed(6);
          } else if ((!la.value || !lo.value) && pinText) {
            pinText.textContent = 'No pin yet';
          }
        };
        map.on('click', function (ev) {
          setCoords(ev.latlng.lat, ev.latlng.lng);
        });
        la.addEventListener('input', syncInputs);
        lo.addEventListener('input', syncInputs);

        var gpsBtn = $('#useLocationBtn');
        if (gpsBtn) {
          gpsBtn.addEventListener('click', function () {
            if (!navigator.geolocation) {
              if (status) status.textContent = 'Geolocation is not supported by this browser.';
              return;
            }
            gpsBtn.disabled = true;
            if (status) status.textContent = 'Detecting your current location…';
            navigator.geolocation.getCurrentPosition(
              function (pos) {
                gpsBtn.disabled = false;
                setCoords(pos.coords.latitude, pos.coords.longitude);
                if (status) status.textContent = 'Location pinned from your device GPS.';
              },
              function () {
                gpsBtn.disabled = false;
                if (status) status.textContent = 'Could not detect location. Click the map or enter coordinates manually.';
              },
              { enableHighAccuracy: true, timeout: 10000 }
            );
          });
        }
      }
    });

    /* Official multi-pin overview map */
    var overviewEl = $('[data-overview-map]');
    var dataEl = $('#mapPointsData');
    if (overviewEl && dataEl) {
      var points = [];
      try {
        points = JSON.parse(dataEl.textContent || '[]');
      } catch (e) {}
      if (points.length) {
        var overviewMap = L.map(overviewEl).setView([points[0].lat, points[0].lng], 14);
        L.tileLayer('https://tile.openstreetmap.de/{z}/{x}/{y}.png', {
          attribution: '&copy; OpenStreetMap contributors',
          maxZoom: 19,
        }).addTo(overviewMap);
        var bounds = [];
        points.forEach(function (pt) {
          var color = pt.is_emergency ? '#DC2626' : '#1E3A5F';
          var fill = pt.is_emergency ? '#FCA5A5' : '#F4A825';
          var wrap = d.createElement('div');
          var link = d.createElement('a');
          link.href = pt.url;
          link.textContent = pt.title;
          link.style.fontWeight = '700';
          var meta = d.createElement('div');
          meta.textContent = pt.category + ' · ' + pt.status;
          meta.style.fontSize = '0.82rem';
          wrap.appendChild(link);
          wrap.appendChild(meta);
          L.circleMarker([pt.lat, pt.lng], { radius: 9, color: color, fillColor: fill, fillOpacity: 0.95 })
            .addTo(overviewMap)
            .bindPopup(wrap);
          bounds.push([pt.lat, pt.lng]);
        });
        if (bounds.length > 1) {
          overviewMap.fitBounds(bounds, { padding: [24, 24], maxZoom: 16 });
        }
        var detailsParent = overviewEl.closest('details');
        if (detailsParent) {
          detailsParent.addEventListener('toggle', function () {
            if (detailsParent.open) {
              setTimeout(function () {
                overviewMap.invalidateSize();
                if (bounds.length > 1) overviewMap.fitBounds(bounds, { padding: [24, 24], maxZoom: 16 });
              }, 80);
            }
          });
        }
      }
    }
  } else if ($('[data-map]')) {
    var mapStatus = $('#mapStatus');
    if (mapStatus) mapStatus.textContent = 'The map could not be initialized. Enter the latitude and longitude manually below.';
  }
})();
