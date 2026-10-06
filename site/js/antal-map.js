// Loads the generated Antal system list and hands it to the Canonn ED3D engine.
// The data file is built by tools/spansh_sync.py from the Spansh galaxy dumps.
(function () {
  var DATA_URL = 'data/antal-systems.json';

  function setStatus(text, isError) {
    var el = document.getElementById('antal-status');
    el.textContent = text;
    el.className = isError ? 'error' : '';
  }

  function hideLoading() {
    var el = document.getElementById('loading');
    if (el) el.style.display = 'none';
  }

  function describe(data) {
    var parts = [data.systems.length.toLocaleString() + ' systems'];
    Object.keys(data.counts || {}).forEach(function (name) {
      parts.push(data.counts[name].toLocaleString() + ' ' + name);
    });
    if (data.dataAsOf) parts.push('data as of ' + data.dataAsOf.slice(0, 16).replace('T', ' ') + ' UTC');
    return parts.join(' · ');
  }

  $.getJSON(DATA_URL + '?t=' + Date.now())
    .done(function (data) {
      if (!data.systems || !data.systems.length) {
        hideLoading();
        setStatus('No systems yet: the data sync has not run.', true);
        return;
      }
      setStatus(describe(data));
      var p = data.position || { x: 0, y: 0, z: 0 };
      Ed3d.init({
        container: 'edmap',
        json: { categories: data.categories, systems: data.systems },
        withFullscreenToggle: false,
        withHudPanel: true,
        hudMultipleSelect: true,
        effectScaleSystem: [20, 500],
        startAnim: true,
        showGalaxyInfos: true,
        playerPos: [p.x, p.y, p.z],
        cameraPos: [p.x, p.y + 400, p.z - 600],
        systemColor: '#ffd84a',
        finished: hideLoading
      });
    })
    .fail(function () {
      hideLoading();
      setStatus('Could not load ' + DATA_URL, true);
    });
})();
