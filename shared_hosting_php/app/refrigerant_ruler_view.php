<?php
declare(strict_types=1);

$refrigerants = [
    ['code'=>'R600a','name'=>'R600a изобутан','type'=>'Бытовые холодильники','bp'=>-11.7,'tc'=>134.7,'pc'=>36.3],
    ['code'=>'R134a','name'=>'R134a тетрафторэтан','type'=>'Старые холодильники, авто','bp'=>-26.1,'tc'=>101.1,'pc'=>40.6],
    ['code'=>'R290','name'=>'R290 пропан','type'=>'Холодильники, моноблоки, тепловые насосы','bp'=>-42.1,'tc'=>96.7,'pc'=>42.5],
    ['code'=>'R12','name'=>'R12','type'=>'Старые системы, запрещён/ограничен','bp'=>-29.8,'tc'=>112.0,'pc'=>41.4],
    ['code'=>'R22','name'=>'R22','type'=>'Старые кондиционеры','bp'=>-40.8,'tc'=>96.1,'pc'=>49.9],
    ['code'=>'R404A','name'=>'R404A','type'=>'Коммерческий холод','bp'=>-46.5,'tc'=>72.1,'pc'=>37.3],
    ['code'=>'R507A','name'=>'R507A','type'=>'Коммерческий холод','bp'=>-46.7,'tc'=>70.9,'pc'=>37.1],
    ['code'=>'R410A','name'=>'R410A','type'=>'Кондиционеры','bp'=>-51.6,'tc'=>72.5,'pc'=>49.0],
    ['code'=>'R32','name'=>'R32','type'=>'Современные кондиционеры','bp'=>-51.7,'tc'=>78.1,'pc'=>57.8],
    ['code'=>'R407C','name'=>'R407C','type'=>'Кондиционеры, смесь с глайдом','bp'=>-43.6,'tc'=>86.7,'pc'=>46.3],
    ['code'=>'R152a','name'=>'R152a','type'=>'Альтернативный хладагент','bp'=>-24.0,'tc'=>113.3,'pc'=>45.2],
    ['code'=>'R1234yf','name'=>'R1234yf','type'=>'Автокондиционеры','bp'=>-29.5,'tc'=>94.7,'pc'=>33.8],
    ['code'=>'R1234ze','name'=>'R1234ze(E)','type'=>'Чиллеры, низкий GWP','bp'=>-19.0,'tc'=>109.4,'pc'=>36.4],
    ['code'=>'R717','name'=>'R717 аммиак','type'=>'Промышленный холод','bp'=>-33.3,'tc'=>132.4,'pc'=>113.5],
    ['code'=>'R744','name'=>'R744 CO₂','type'=>'CO₂, транскритические системы','bp'=>-78.5,'tc'=>31.0,'pc'=>73.8],
    ['code'=>'R600','name'=>'R600 бутан','type'=>'Редко, углеводород','bp'=>-0.5,'tc'=>152.0,'pc'=>38.0],
    ['code'=>'R1270','name'=>'R1270 пропилен','type'=>'Низкотемпературный холод','bp'=>-47.7,'tc'=>91.1,'pc'=>46.0],
    ['code'=>'R502','name'=>'R502','type'=>'Старый коммерческий холод','bp'=>-45.4,'tc'=>82.2,'pc'=>40.7],
];
$refrigerantByCode = [];
foreach ($refrigerants as $ref) $refrigerantByCode[$ref['code']] = $ref;
$atmosphericPressure = 1.01325;
$selectedCode = (string)($_POST['refrigerant'] ?? 'R410A');
$mode = (string)($_POST['mode'] ?? 'temperature');
$rawValue = trim((string)($_POST['value'] ?? '10'));
$rulerResult = null;
$rulerError = '';
$rulerClamped = false;
$calcSaveMessage = ''; $calcSaveError = '';
$engineeringAdmin = (bool)admin_user();
$engineeringProjects = $engineeringAdmin ? engineering_projects_for_current_admin() : [];
$selectedProjectId = (int)($_POST['project_id'] ?? 0);
$pressureAbs = static function (array $ref, float $temperature) use ($atmosphericPressure): float {
    $boilingK = $ref['bp'] + 273.15;
    $criticalK = $ref['tc'] + 273.15;
    $slope = log($ref['pc'] / $atmosphericPressure) / ((1.0 / $boilingK) - (1.0 / $criticalK));
    $intercept = log($atmosphericPressure) + $slope / $boilingK;
    $temperatureK = $temperature + 273.15;
    return exp($intercept - $slope / $temperatureK);
};
if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST' && (string)($_POST['tool'] ?? '') === 'refrigerant') {
    verify_csrf();
    if (!isset($refrigerantByCode[$selectedCode]) || !in_array($mode, ['pressure','temperature'], true)) {
        $rulerError = 'Выберите хладагент и направление пересчёта.';
    } elseif ($rawValue === '' || !is_numeric(str_replace(',', '.', $rawValue)) || !is_finite((float)str_replace(',', '.', $rawValue))) {
        $rulerError = 'Введите конечное числовое значение.';
    } else {
        $ref = $refrigerantByCode[$selectedCode];
        $value = (float)str_replace(',', '.', $rawValue);
        $minimumTemp = max($ref['bp'] - 30.0, -80.0);
        $maximumTemp = min($ref['tc'] - 5.0, 90.0);
        $minimumPressure = max(-0.99, min($pressureAbs($ref, $minimumTemp) - $atmosphericPressure, 0.0));
        $maximumPressure = min(max($pressureAbs($ref, $maximumTemp) - $atmosphericPressure, 1.0), 80.0);
        if ($mode === 'pressure') {
            $pressureGauge = min(max($value, $minimumPressure), $maximumPressure);
            $rulerClamped = abs($pressureGauge - $value) > 0.00001;
            $pressureAbsolute = max($pressureGauge + $atmosphericPressure, 0.02);
            $boilingK = $ref['bp'] + 273.15;
            $criticalK = $ref['tc'] + 273.15;
            $slope = log($ref['pc'] / $atmosphericPressure) / ((1.0 / $boilingK) - (1.0 / $criticalK));
            $intercept = log($atmosphericPressure) + $slope / $boilingK;
            $temperature = $slope / ($intercept - log($pressureAbsolute)) - 273.15;
            $temperature = min(max($temperature, $minimumTemp), $maximumTemp);
        } else {
            $temperature = min(max($value, $minimumTemp), $maximumTemp);
            $rulerClamped = abs($temperature - $value) > 0.00001;
            $pressureAbsolute = $pressureAbs($ref, $temperature);
            $pressureGauge = $pressureAbsolute - $atmosphericPressure;
        }
        $zone = $temperature <= -30 ? 'Низкотемпературное кипение' : ($temperature <= -10 ? 'Испарение бытового холодильника' : ($temperature <= 10 ? 'Околонулевая зона / кондиционирование' : ($temperature <= 45 ? 'Конденсация / тёплая сторона' : 'Высокая температура конденсации')));
        $rulerResult = [
            'ref'=>$ref, 'temperature'=>$temperature, 'pressure_gauge'=>$pressureGauge,
            'pressure_absolute'=>$pressureAbsolute, 'minimum_temp'=>$minimumTemp,
            'maximum_temp'=>$maximumTemp, 'minimum_pressure'=>$minimumPressure,
            'maximum_pressure'=>$maximumPressure, 'zone'=>$zone,
        ];
        if (!empty($_POST['save_to_project']) && $engineeringAdmin) {
            try {
                save_engineering_calculation(db(), $selectedProjectId, 'refrigeration', 'Линейка холодильщика — ' . $selectedCode, ['refrigerant'=>$selectedCode,'mode'=>$mode,'value'=>$rawValue], $rulerResult);
                $calcSaveMessage = 'Результат сохранён в инженерную историю проекта.';
            } catch (Throwable $saveException) {
                error_log('Save refrigerant calculation failed: ' . $saveException->getMessage());
                $calcSaveError = $saveException->getMessage();
            }
        }
    }
}
?>
<section class="page-hero"><div class="wrap"><p class="eyebrow">ИНЖЕНЕРНЫЕ ИНСТРУМЕНТЫ / ХОЛОД</p><h1>Линейка холодильщика</h1><p>Приближённый пересчёт давления насыщения и температуры для распространённых хладагентов.</p></div></section>
<section class="section wrap">
  <?php if ($rulerError !== ''): ?><div class="notice error"><?= e($rulerError) ?></div><?php endif; ?>
  <?php if ($calcSaveMessage !== ''): ?><div class="notice success"><?= e($calcSaveMessage) ?></div><?php endif; ?>
  <?php if ($calcSaveError !== ''): ?><div class="notice error"><?= e($calcSaveError) ?></div><?php endif; ?>
  <div class="calc-layout refrigerant-layout">
    <div class="calc-card"><p class="eyebrow">ПАРАМЕТРЫ</p><h2>Давление ↔ температура</h2>
      <form method="post" action="<?= e(site_path('index.php?page=refrigerant-ruler')) ?>">
        <input type="hidden" name="_csrf" value="<?= e(csrf_token()) ?>"><input type="hidden" name="tool" value="refrigerant">
        <label>Хладагент<select name="refrigerant"><?php foreach ($refrigerants as $ref): ?><option value="<?= e($ref['code']) ?>" <?= $selectedCode === $ref['code'] ? 'selected' : '' ?>><?= e($ref['code'] . ' — ' . $ref['name']) ?></option><?php endforeach; ?></select></label>
        <label>Что известно<select name="mode"><option value="temperature" <?= $mode === 'temperature' ? 'selected' : '' ?>>Температура насыщения, °C</option><option value="pressure" <?= $mode === 'pressure' ? 'selected' : '' ?>>Манометрическое давление, bar</option></select></label>
        <label><?= $mode === 'pressure' ? 'Давление по манометру, bar' : 'Температура, °C' ?><input type="number" name="value" step="any" required value="<?= e($rawValue) ?>"></label>
        <?php if ($engineeringAdmin): ?><?php if ($engineeringProjects): ?><div class="engineering-save-to-project"><label>Проект для сохранения результата<select name="project_id"><option value="0">Не выбран</option><?php foreach ($engineeringProjects as $engineeringProject): ?><option value="<?= (int)$engineeringProject['id'] ?>" <?= $selectedProjectId===(int)$engineeringProject['id']?'selected':'' ?>><?= e($engineeringProject['title']) ?></option><?php endforeach; ?></select></label><label class="check-label"><input type="checkbox" name="save_to_project" value="1" <?= !empty($_POST['save_to_project'])?'checked':'' ?>> Сохранить результат в Engineering OS</label></div><?php else: ?><p class="muted small">Создайте проект во вкладке Engineering OS, чтобы сохранять расчёты.</p><?php endif; ?><?php endif; ?>
        <button class="button">Пересчитать ↗</button>
      </form>
    </div>
    <div class="calc-result">
      <?php if ($rulerResult): ?>
        <p class="eyebrow">РЕЗУЛЬТАТ / <?= e($rulerResult['ref']['code']) ?></p>
        <strong><?= number_format($rulerResult['temperature'], 1, ',', ' ') ?> <small>°C</small></strong>
        <p><?= e($rulerResult['ref']['name']) ?> · <?= e($rulerResult['zone']) ?></p>
        <div class="vent-result-metrics">
          <div><span>Давление по манометру</span><b><?= number_format($rulerResult['pressure_gauge'], 2, ',', ' ') ?> bar</b></div>
          <div><span>Абсолютное давление</span><b><?= number_format($rulerResult['pressure_absolute'], 2, ',', ' ') ?> bar(a)</b></div>
          <div><span>Нормальная температура кипения</span><b><?= number_format($rulerResult['ref']['bp'], 1, ',', ' ') ?> °C</b></div>
          <div><span>Критическая температура</span><b><?= number_format($rulerResult['ref']['tc'], 1, ',', ' ') ?> °C</b></div>
          <div><span>Критическое давление</span><b><?= number_format($rulerResult['ref']['pc'], 1, ',', ' ') ?> bar(a)</b></div>
        </div>
        <?php if ($rulerClamped): ?><div class="notice warning">Значение вышло за диапазон этой приближённой модели и было ограничено допустимой границей.</div><?php endif; ?>
      <?php else: ?>
        <div class="result-orbit">bar ↔ °C</div><h2>Линейка насыщения</h2><p>Выберите хладагент и введите температуру или давление. Результат появится здесь.</p>
      <?php endif; ?>
    </div>
  </div>
  <div class="notice warning">Это математическая аппроксимация по нормальной температуре кипения и критической точке, а не таблица производителя. Не используйте её как единственный источник при заправке или диагностике. Для хладагентов с требованиями по горючести/токсичности соблюдайте документацию производителя и правила безопасности.</div>
  <section class="section"><div class="section-heading"><div><p class="eyebrow">СПРАВОЧНИК</p><h2>Доступные хладагенты</h2></div></div><div class="table-panel"><table><thead><tr><th>Код</th><th>Применение</th><th>Кипение, °C</th><th>Критическая точка, °C</th><th>Критическое давление, bar(a)</th></tr></thead><tbody><?php foreach ($refrigerants as $ref): ?><tr><td><?= e($ref['code']) ?></td><td><?= e($ref['type']) ?></td><td><?= number_format($ref['bp'],1,',',' ') ?></td><td><?= number_format($ref['tc'],1,',',' ') ?></td><td><?= number_format($ref['pc'],1,',',' ') ?></td></tr><?php endforeach; ?></tbody></table></div></section>
</section>
