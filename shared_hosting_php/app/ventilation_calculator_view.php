<?php
declare(strict_types=1);

$roomTypes = [
    'office' => ['Офисы', 2.5, 1.5],
    'shop' => ['Магазины и ТЦ', 1.5, 1.2],
    'cafe' => ['Кафе и рестораны', 3.0, 1.8],
    'production' => ['Производства и цеха', 2.5, 1.0],
    'warehouse' => ['Склады', 1.0, 1.2],
    'fitness' => ['Фитнес-центры', 5.0, 1.2],
    'spa' => ['Бассейны и СПА', 7.0, 1.4],
    'medical' => ['Медицинские учреждения', 3.0, 1.5],
    'residential' => ['Квартиры и частные дома', 2.0, 1.5],
    'school' => ['Школы и детские учреждения', 2.5, 1.3],
    'datacenter' => ['Серверные и дата-центры', 10.0, 2.0],
];
$systemTypes = [
    'supply_exhaust' => ['Приточно-вытяжная', 'balanced', 1.0, []],
    'supply' => ['Приточная', 'supply', 0.6, []],
    'exhaust' => ['Вытяжная', 'exhaust', 0.4, []],
    'recovery' => ['Приточно-вытяжная с рекуперацией', 'balanced', 1.0, ['recovery']],
    'cooling' => ['Приточно-вытяжная с охлаждением', 'balanced', 1.0, ['cooling']],
];
$ventDefaults = [
    'area' => '120', 'height' => '2.75', 'people' => '25', 'room_type' => 'office',
    'ventilation_type' => 'supply_exhaust', 'air_changes' => '0', 'required_flow' => '0',
    'equipment_capacity' => '0', 'temperature_delta' => '10', 'duct_length' => '25',
    'duct_diameter' => '0', 'branches' => '0', 'grilles' => '0', 'diffusers' => '0',
    'fans' => '0', 'recuperators' => '0', 'filters' => '0', 'silencers' => '0',
    'valves' => '0', 'automation' => '1', 'mounting' => '1', 'additional_work' => '0',
];
$ventValues = $ventDefaults;
$ventResult = null;
$ventError = '';
$ventPrices = [
    'ventilation.people_airflow' => 40,
    'ventilation.supply_factor' => 1,
    'ventilation.exhaust_factor' => 1,
    'ventilation.fan_reserve_percent' => 15,
    'ventilation.duct_velocity' => 4,
    'ventilation.rounding_step' => 10,
    'ventilation.duct_rounding_step' => 5,
    'ventilation.price_equipment_base' => 20000,
    'ventilation.price_automation' => 40000,
    'ventilation.price_ducts_m2' => 155,
    'ventilation.price_grille' => 480,
    'ventilation.price_diffuser' => 650,
    'ventilation.price_fan' => 18000,
    'ventilation.price_recovery' => 85000,
    'ventilation.price_filter' => 6500,
    'ventilation.price_silencer' => 8500,
    'ventilation.price_valve' => 3200,
    'ventilation.price_cooling' => 45000,
    'ventilation.cooling_capacity_per_unit' => 8,
    'ventilation.heat_capacity' => 0.335,
    'ventilation.price_materials_percent' => 15,
    'ventilation.installation_percent' => 50,
    'ventilation.duct_installation_percent' => 80,
    'ventilation.commissioning_percent' => 10,
    'ventilation.additional_percent' => 3,
    'ventilation.recovery_default' => 70,
];
$vp = [];
foreach ($ventPrices as $key => $default) {
    $raw = setting($key, (string)$default);
    $value = is_numeric(str_replace(',', '.', $raw)) ? (float)str_replace(',', '.', $raw) : (float)$default;
    $vp[$key] = is_finite($value) && $value >= 0 ? min($value, 100000000) : (float)$default;
}
$ventMoney = static fn(float $amount): int => (int)(ceil(max(0, $amount) / max(1, $vp['ventilation.rounding_step'])) * max(1, $vp['ventilation.rounding_step']));
$ventNum = static function (array $source, string $key, float $min, float $max, bool $integer = false): float|int {
    $raw = trim((string)($source[$key] ?? ''));
    if ($raw === '' || !is_numeric(str_replace(',', '.', $raw))) {
        throw new InvalidArgumentException('Проверьте поле «' . $key . '» — требуется число.');
    }
    $value = (float)str_replace(',', '.', $raw);
    if (!is_finite($value) || $value < $min || $value > $max || ($integer && floor($value) !== $value)) {
        throw new InvalidArgumentException('Значение поля «' . $key . '» вне допустимого диапазона.');
    }
    return $integer ? (int)$value : $value;
};

if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST' && (string)($_POST['tool'] ?? '') === 'ventilation') {
    verify_csrf();
    foreach ($ventDefaults as $key => $default) {
        $ventValues[$key] = is_string($_POST[$key] ?? null) ? trim((string)$_POST[$key]) : $default;
    }
    try {
        $area = (float)$ventNum($ventValues, 'area', 10, 5000);
        $height = (float)$ventNum($ventValues, 'height', 2, 7);
        $people = (int)$ventNum($ventValues, 'people', 1, 5000, true);
        $airChangesInput = (float)$ventNum($ventValues, 'air_changes', 0, 100);
        $requiredFlow = (float)$ventNum($ventValues, 'required_flow', 0, 10000000);
        $equipmentCapacity = (float)$ventNum($ventValues, 'equipment_capacity', 0, 10000000);
        $temperatureDelta = (float)$ventNum($ventValues, 'temperature_delta', 0, 60);
        $ductLength = (float)$ventNum($ventValues, 'duct_length', 0, 100000);
        $ductDiameter = (float)$ventNum($ventValues, 'duct_diameter', 0, 5000);
        $branches = (int)$ventNum($ventValues, 'branches', 0, 100000, true);
        $grilles = (int)$ventNum($ventValues, 'grilles', 0, 100000, true);
        $diffusers = (int)$ventNum($ventValues, 'diffusers', 0, 100000, true);
        $fans = (int)$ventNum($ventValues, 'fans', 0, 10000, true);
        $recuperators = (int)$ventNum($ventValues, 'recuperators', 0, 10000, true);
        $filters = (int)$ventNum($ventValues, 'filters', 0, 100000, true);
        $silencers = (int)$ventNum($ventValues, 'silencers', 0, 100000, true);
        $valves = (int)$ventNum($ventValues, 'valves', 0, 100000, true);
        $automation = (int)$ventNum($ventValues, 'automation', 0, 10000, true);
        $mounting = (float)$ventNum($ventValues, 'mounting', 0, 1);
        $additionalWork = (float)$ventNum($ventValues, 'additional_work', 0, 100000000);
        $roomCode = (string)$ventValues['room_type'];
        $systemCode = (string)$ventValues['ventilation_type'];
        if (!isset($roomTypes[$roomCode]) || !isset($systemTypes[$systemCode])) {
            throw new InvalidArgumentException('Выберите назначение помещения и тип вентиляции из списка.');
        }
        [$roomName, $roomChanges, $roomFactor] = $roomTypes[$roomCode];
        [$systemName, $mode, $systemShare, $features] = $systemTypes[$systemCode];
        $configuredChanges = $airChangesInput > 0 ? $airChangesInput : $roomChanges;
        $volume = $area * $height;
        $exchangeFlow = max($volume * $configuredChanges, $people * $vp['ventilation.people_airflow'], $requiredFlow);
        $supplyEnabled = $mode !== 'exhaust';
        $exhaustEnabled = $mode !== 'supply';
        $supplyFlow = $supplyEnabled ? $exchangeFlow * $vp['ventilation.supply_factor'] : 0;
        $exhaustFlow = $exhaustEnabled ? $exchangeFlow * $vp['ventilation.exhaust_factor'] : 0;
        $designFlow = max($supplyFlow, $exhaustFlow, $equipmentCapacity);
        $thermalPower = $designFlow * $temperatureDelta * $vp['ventilation.heat_capacity'] / 1000;
        $recoveryPower = in_array('recovery', $features, true) ? $thermalPower * $vp['ventilation.recovery_default'] / 100 : 0;
        $coolingUnits = in_array('cooling', $features, true) && $thermalPower > 0
            ? (int)ceil($thermalPower / max(0.1, $vp['ventilation.cooling_capacity_per_unit'])) : 0;
        $fanFlow = $designFlow * (1 + $vp['ventilation.fan_reserve_percent'] / 100);
        $ductArea = $fanFlow > 0 ? $fanFlow / 3600 / max(0.1, $vp['ventilation.duct_velocity']) : 0;
        $step = max(1, (int)$vp['ventilation.duct_rounding_step']);
        $diameter = $ductDiameter > 0 ? $ductDiameter : ($ductArea > 0 ? sqrt(4 * $ductArea / pi()) * 1000 : 0);
        $recommendedDiameter = $diameter > 0 ? (int)(ceil($diameter / $step) * $step) : 0;
        $side = $ductArea > 0 ? (int)(ceil(sqrt($ductArea) * 1000 / $step) * $step) : 0;
        $estimatedGrilles = $supplyEnabled ? ($grilles ?: max(1, (int)ceil($supplyFlow / 150))) : 0;
        $estimatedDiffusers = $supplyEnabled ? ($diffusers ?: max(1, (int)ceil($supplyFlow / 120))) : 0;
        $estimatedFans = $fans ?: ($designFlow > 0 ? 1 : 0);
        $estimatedBranches = $branches ?: ($designFlow > 0 ? max(1, (int)ceil($designFlow / 500)) : 0);
        $estimatedRecuperators = in_array('recovery', $features, true) ? max($recuperators, 1) : $recuperators;
        $equipmentCost = $vp['ventilation.price_equipment_base'] * $roomFactor * $systemShare;
        $equipmentCost += $estimatedFans * $vp['ventilation.price_fan'];
        $equipmentCost += $estimatedRecuperators * $vp['ventilation.price_recovery'];
        $equipmentCost += $coolingUnits * $vp['ventilation.price_cooling'];
        $equipmentCost += $filters * $vp['ventilation.price_filter'];
        $equipmentCost += $silencers * $vp['ventilation.price_silencer'];
        $equipmentCost += $valves * $vp['ventilation.price_valve'];
        $ductsCost = $ductLength * $vp['ventilation.price_ducts_m2'];
        $distributionCost = $estimatedGrilles * $vp['ventilation.price_grille'] + $estimatedDiffusers * $vp['ventilation.price_diffuser'];
        $automationCost = $automation * $vp['ventilation.price_automation'];
        $materialsCost = ($equipmentCost + $ductsCost + $distributionCost + $automationCost) * $vp['ventilation.price_materials_percent'] / 100;
        $installationCost = ($equipmentCost * $vp['ventilation.installation_percent'] / 100 + $ductsCost * $vp['ventilation.duct_installation_percent'] / 100) * $mounting;
        $commissioningCost = $installationCost * $vp['ventilation.commissioning_percent'] / 100;
        $additionalCost = $additionalWork + ($equipmentCost + $ductsCost) * $vp['ventilation.additional_percent'] / 100;
        $breakdown = [
            ['Оборудование', $ventMoney($equipmentCost)],
            ['Воздуховоды', $ventMoney($ductsCost)],
            ['Решётки и диффузоры', $ventMoney($distributionCost)],
            ['Автоматика', $ventMoney($automationCost)],
            ['Расходные материалы', $ventMoney($materialsCost)],
            ['Монтаж', $ventMoney($installationCost)],
            ['Пусконаладка', $ventMoney($commissioningCost)],
            ['Дополнительные расходы', $ventMoney($additionalCost)],
        ];
        $total = array_sum(array_column($breakdown, 1));
        $ventResult = [
            'room' => $roomName, 'system' => $systemName, 'volume' => $volume,
            'air_exchange' => $exchangeFlow, 'supply' => $supplyFlow, 'exhaust' => $exhaustFlow,
            'fan' => $fanFlow, 'cooling_capacity' => in_array('cooling', $features, true) ? $thermalPower : 0,
            'recovery_power' => $recoveryPower, 'diameter' => $recommendedDiameter,
            'rect' => $side > 0 ? ($side * 2) . ' × ' . $side . ' мм' : '—',
            'branches' => $estimatedBranches, 'grilles' => $estimatedGrilles,
            'diffusers' => $estimatedDiffusers, 'fans' => $estimatedFans,
            'recuperators' => $estimatedRecuperators, 'cooling_units' => $coolingUnits,
            'total' => $ventMoney($total), 'breakdown' => $breakdown,
        ];
    } catch (InvalidArgumentException $exception) {
        $ventError = $exception->getMessage();
    }
}
?>
<section class="page-hero"><div class="wrap"><p class="eyebrow">ИНЖЕНЕРНЫЕ ИНСТРУМЕНТЫ / ВЕНТИЛЯЦИЯ</p><h1>Расчёт вентиляции</h1><p>Отдельный предварительный расчёт воздухообмена, сечения воздуховода и бюджета оборудования с монтажом.</p></div></section>
<section class="section wrap">
  <?php if ($ventError !== ''): ?><div class="notice error"><?= e($ventError) ?></div><?php endif; ?>
  <div class="calc-layout ventilation-calc-layout">
    <div class="calc-card">
      <p class="eyebrow">ВХОДНЫЕ ДАННЫЕ</p><h2>Параметры объекта</h2>
      <form method="post" action="<?= e(site_path('index.php?page=ventilation-calculator')) ?>">
        <input type="hidden" name="_csrf" value="<?= e(csrf_token()) ?>"><input type="hidden" name="tool" value="ventilation">
        <div class="form-grid">
          <label>Назначение помещения<select name="room_type"><?php foreach ($roomTypes as $code => $room): ?><option value="<?= e($code) ?>" <?= $ventValues['room_type'] === $code ? 'selected' : '' ?>><?= e($room[0]) ?></option><?php endforeach; ?></select></label>
          <label>Тип системы<select name="ventilation_type"><?php foreach ($systemTypes as $code => $system): ?><option value="<?= e($code) ?>" <?= $ventValues['ventilation_type'] === $code ? 'selected' : '' ?>><?= e($system[0]) ?></option><?php endforeach; ?></select></label>
          <label>Площадь, м²<input type="number" name="area" min="10" max="5000" step="0.1" required value="<?= e($ventValues['area']) ?>"></label>
          <label>Высота, м<input type="number" name="height" min="2" max="7" step="0.05" required value="<?= e($ventValues['height']) ?>"></label>
          <label>Количество людей<input type="number" name="people" min="1" max="5000" step="1" required value="<?= e($ventValues['people']) ?>"></label>
          <label>Кратность воздухообмена, 0 = авто<input type="number" name="air_changes" min="0" max="100" step="0.1" value="<?= e($ventValues['air_changes']) ?>"></label>
          <label>Требуемый расход воздуха, м³/ч<input type="number" name="required_flow" min="0" max="10000000" step="1" value="<?= e($ventValues['required_flow']) ?>"></label>
          <label>Производительность выбранной установки, м³/ч<input type="number" name="equipment_capacity" min="0" max="10000000" step="1" value="<?= e($ventValues['equipment_capacity']) ?>"></label>
          <label>Перепад температуры, °C<input type="number" name="temperature_delta" min="0" max="60" step="0.5" value="<?= e($ventValues['temperature_delta']) ?>"></label>
          <label>Длина воздуховодов, м<input type="number" name="duct_length" min="0" max="100000" step="0.1" value="<?= e($ventValues['duct_length']) ?>"></label>
          <label>Заданный диаметр, мм (0 = авто)<input type="number" name="duct_diameter" min="0" max="5000" step="5" value="<?= e($ventValues['duct_diameter']) ?>"></label>
          <label>Ветви, 0 = авто<input type="number" name="branches" min="0" max="100000" step="1" value="<?= e($ventValues['branches']) ?>"></label>
          <label>Решётки, 0 = авто<input type="number" name="grilles" min="0" max="100000" step="1" value="<?= e($ventValues['grilles']) ?>"></label>
          <label>Диффузоры, 0 = авто<input type="number" name="diffusers" min="0" max="100000" step="1" value="<?= e($ventValues['diffusers']) ?>"></label>
          <label>Вентиляторы, 0 = авто<input type="number" name="fans" min="0" max="10000" step="1" value="<?= e($ventValues['fans']) ?>"></label>
          <label>Рекуператоры<input type="number" name="recuperators" min="0" max="10000" step="1" value="<?= e($ventValues['recuperators']) ?>"></label>
          <label>Фильтры<input type="number" name="filters" min="0" max="100000" step="1" value="<?= e($ventValues['filters']) ?>"></label>
          <label>Шумоглушители<input type="number" name="silencers" min="0" max="100000" step="1" value="<?= e($ventValues['silencers']) ?>"></label>
          <label>Клапаны<input type="number" name="valves" min="0" max="100000" step="1" value="<?= e($ventValues['valves']) ?>"></label>
          <label>Комплекты автоматики<input type="number" name="automation" min="0" max="10000" step="1" value="<?= e($ventValues['automation']) ?>"></label>
          <label>Монтаж<select name="mounting"><option value="1" <?= $ventValues['mounting'] === '1' ? 'selected' : '' ?>>Включить 100%</option><option value="0.5" <?= $ventValues['mounting'] === '0.5' ? 'selected' : '' ?>>Условно 50%</option><option value="0" <?= $ventValues['mounting'] === '0' ? 'selected' : '' ?>>Без монтажа</option></select></label>
          <label>Дополнительные работы, ₽<input type="number" name="additional_work" min="0" max="100000000" step="100" value="<?= e($ventValues['additional_work']) ?>"></label>
        </div>
        <button class="button">Рассчитать вентиляцию ↗</button>
      </form>
    </div>
    <div class="calc-result">
      <?php if ($ventResult): ?>
        <p class="eyebrow">ПРЕДВАРИТЕЛЬНЫЙ РЕЗУЛЬТАТ</p><strong><?= number_format($ventResult['total'], 0, ',', ' ') ?> <small>₽</small></strong>
        <p><?= e($ventResult['room']) ?> · <?= e($ventResult['system']) ?></p>
        <div class="vent-result-metrics">
          <div><span>Воздухообмен</span><b><?= number_format($ventResult['air_exchange'], 0, ',', ' ') ?> м³/ч</b></div>
          <div><span>Приток / вытяжка</span><b><?= number_format($ventResult['supply'], 0, ',', ' ') ?> / <?= number_format($ventResult['exhaust'], 0, ',', ' ') ?> м³/ч</b></div>
          <div><span>Объём помещения</span><b><?= number_format($ventResult['volume'], 1, ',', ' ') ?> м³</b></div>
          <div><span>Расчётный поток с резервом</span><b><?= number_format($ventResult['fan'], 0, ',', ' ') ?> м³/ч</b></div>
          <div><span>Круглый воздуховод</span><b><?= $ventResult['diameter'] ? 'Ø ' . (int)$ventResult['diameter'] . ' мм' : '—' ?></b></div>
          <div><span>Прямоугольный канал</span><b><?= e($ventResult['rect']) ?></b></div>
          <div><span>Рекуперация / охлаждение</span><b><?= number_format($ventResult['recovery_power'], 1, ',', ' ') ?> / <?= number_format($ventResult['cooling_capacity'], 1, ',', ' ') ?> кВт</b></div>
        </div>
        <h3>Состав предварительной сметы</h3><table><thead><tr><th>Статья</th><th>Сумма</th></tr></thead><tbody><?php foreach ($ventResult['breakdown'] as [$label,$value]): ?><tr><td><?= e($label) ?></td><td><?= number_format($value, 0, ',', ' ') ?> ₽</td></tr><?php endforeach; ?></tbody></table>
      <?php else: ?>
        <div class="result-orbit">m³/h</div><h2>Что будет рассчитано</h2><p>Расход воздуха, резерв производительности, рекомендуемый диаметр воздуховода, ориентировочные количества компонентов и бюджет с разбивкой по статьям.</p>
      <?php endif; ?>
    </div>
  </div>
  <div class="notice warning">Результат предварительный. Для рабочего проекта необходимо проверить нормативный воздухообмен, аэродинамическое сопротивление сети, шум, пожарные требования, баланс потоков и реальные характеристики оборудования. Тарифы редактируются в админ-панели.</div>
</section>
