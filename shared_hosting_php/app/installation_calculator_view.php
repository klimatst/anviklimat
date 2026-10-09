<?php
declare(strict_types=1);

$installRates = [
    'installation.pricing.acStandard' => 8500,
    'installation.pricing.acPremium' => 12000,
    'installation.pricing.acAdditionalRoute' => 1200,
    'installation.pricing.vrfMainRoute' => 2800,
    'installation.pricing.vrfBranch' => 4200,
    'installation.pricing.outdoorUnit' => 6500,
    'installation.pricing.indoorUnit' => 3500,
    'installation.pricing.commissioning' => 6500,
    'installation.pricing.pressureTest' => 3200,
    'installation.pricing.vacuum' => 1800,
    'installation.pricing.refrigerantCharge' => 1200,
    'installation.pricing.electricalConnection' => 2800,
    'installation.pricing.condensatePumpInstall' => 4500,
    'installation.pricing.coreDrilling' => 1800,
    'installation.pricing.liftHour' => 6500,
    'installation.pricing.scaffoldShift' => 4200,
];
$ir = [];
foreach ($installRates as $key => $default) {
    $raw = setting($key, (string)$default);
    $value = is_numeric(str_replace(',', '.', $raw)) ? (float)str_replace(',', '.', $raw) : (float)$default;
    $ir[$key] = is_finite($value) && $value >= 0 ? min($value, 10000000) : (float)$default;
}
$installDefaults = [
    'profile'=>'ac','units'=>'1','outdoor_units'=>'1','route_length'=>'5','branches'=>'0',
    'floor_count'=>'1','complexity'=>'standard','commissioning'=>'1','pressure_test'=>'1',
    'vacuum'=>'1','electrical'=>'1','pump_count'=>'0','drilling_count'=>'0',
    'lift_hours'=>'0','scaffold_shifts'=>'0','refrigerant_kg'=>'0',
];
$installValues = $installDefaults;
$installResult = null;
$installError = '';
$installNumber = static function (array $source, string $key, float $min, float $max, bool $integer = false): float|int {
    $raw = trim((string)($source[$key] ?? ''));
    if ($raw === '' || !is_numeric(str_replace(',', '.', $raw))) throw new InvalidArgumentException('Проверьте числовое поле «' . $key . '».');
    $value = (float)str_replace(',', '.', $raw);
    if (!is_finite($value) || $value < $min || $value > $max || ($integer && floor($value) !== $value)) {
        throw new InvalidArgumentException('Значение поля «' . $key . '» вне допустимого диапазона.');
    }
    return $integer ? (int)$value : $value;
};
if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST' && (string)($_POST['tool'] ?? '') === 'installation') {
    verify_csrf();
    foreach ($installDefaults as $key => $default) $installValues[$key] = is_string($_POST[$key] ?? null) ? trim((string)$_POST[$key]) : $default;
    try {
        $profile = (string)$installValues['profile'];
        $complexity = (string)$installValues['complexity'];
        if (!in_array($profile, ['ac','vrf_vrv'], true) || !in_array($complexity, ['standard','limited_access','height_work'], true)) {
            throw new InvalidArgumentException('Выберите тип системы и сложность монтажа.');
        }
        $units = (int)$installNumber($installValues,'units',1,500,true);
        $outdoorUnits = (int)$installNumber($installValues,'outdoor_units',1,100,true);
        $routeLength = (float)$installNumber($installValues,'route_length',0,100000);
        $branches = (int)$installNumber($installValues,'branches',0,100000,true);
        $floors = (int)$installNumber($installValues,'floor_count',1,500,true);
        $pumpCount = (int)$installNumber($installValues,'pump_count',0,10000,true);
        $drillingCount = (int)$installNumber($installValues,'drilling_count',0,100000,true);
        $liftHours = (float)$installNumber($installValues,'lift_hours',0,100000);
        $scaffoldShifts = (float)$installNumber($installValues,'scaffold_shifts',0,100000);
        $refrigerantKg = (float)$installNumber($installValues,'refrigerant_kg',0,100000);
        foreach (['commissioning','pressure_test','vacuum','electrical'] as $key) {
            if (!in_array($installValues[$key], ['0','1'], true)) throw new InvalidArgumentException('Проверьте дополнительные работы.');
        }
        $complexityFactor = ['standard'=>1.0,'limited_access'=>1.25,'height_work'=>1.5][$complexity];
        $lines = [];
        $addLine = static function (string $label, float $quantity, string $unit, float $unitPrice) use (&$lines): void {
            if ($quantity <= 0 || $unitPrice <= 0) return;
            $lines[] = ['label'=>$label,'quantity'=>$quantity,'unit'=>$unit,'unit_price'=>$unitPrice,'total'=>round($quantity*$unitPrice,2)];
        };
        if ($profile === 'ac') {
            $baseRate = $complexity === 'standard' ? $ir['installation.pricing.acStandard'] : $ir['installation.pricing.acPremium'];
            $addLine('Монтаж сплит-системы', $units, 'компл.', $baseRate * $complexityFactor);
            $addLine('Дополнительная трасса кондиционера', $routeLength, 'м', $ir['installation.pricing.acAdditionalRoute'] * $complexityFactor);
        } else {
            $addLine('Монтаж внутренних блоков VRV / VRF', $units, 'шт.', $ir['installation.pricing.indoorUnit'] * $complexityFactor);
            $addLine('Монтаж наружных блоков VRV / VRF', $outdoorUnits, 'шт.', $ir['installation.pricing.outdoorUnit'] * $complexityFactor);
            $addLine('Прокладка магистрали VRV / VRF', $routeLength, 'м', $ir['installation.pricing.vrfMainRoute'] * $complexityFactor);
            $addLine('Монтаж ответвлений / рефнетов', $branches, 'шт.', $ir['installation.pricing.vrfBranch'] * $complexityFactor);
        }
        $addLine('Работы с учётом этажности', $floors, 'этаж', 0);
        if ($installValues['commissioning'] === '1') $addLine('Пусконаладка', 1, 'усл.', $ir['installation.pricing.commissioning']);
        if ($installValues['pressure_test'] === '1') $addLine('Опрессовка азотом', 1, 'усл.', $ir['installation.pricing.pressureTest']);
        if ($installValues['vacuum'] === '1') $addLine('Вакуумирование системы', 1, 'усл.', $ir['installation.pricing.vacuum']);
        if ($installValues['electrical'] === '1') $addLine('Электрическое подключение', 1, 'усл.', $ir['installation.pricing.electricalConnection']);
        $addLine('Монтаж дренажной помпы', $pumpCount, 'шт.', $ir['installation.pricing.condensatePumpInstall']);
        $addLine('Алмазное бурение / проходка', $drillingCount, 'шт.', $ir['installation.pricing.coreDrilling']);
        $addLine('Подъёмник / автовышка', $liftHours, 'ч', $ir['installation.pricing.liftHour']);
        $addLine('Леса / высотные работы', $scaffoldShifts, 'смена', $ir['installation.pricing.scaffoldShift']);
        $addLine('Дозаправка хладагентом', $refrigerantKg, 'кг', $ir['installation.pricing.refrigerantCharge']);
        $total = array_sum(array_column($lines, 'total'));
        $installResult = [
            'profile'=>$profile,'complexity'=>$complexity,'units'=>$units,'outdoor_units'=>$outdoorUnits,
            'route_length'=>$routeLength,'branches'=>$branches,'factor'=>$complexityFactor,
            'lines'=>$lines,'total'=>round($total,2),
        ];
    } catch (InvalidArgumentException $exception) {
        $installError = $exception->getMessage();
    }
}
?>
<section class="page-hero"><div class="wrap"><p class="eyebrow">ИНЖЕНЕРНЫЕ ИНСТРУМЕНТЫ / МОНТАЖ</p><h1>Расчёт стоимости монтажа</h1><p>Отдельный калькулятор монтажных работ для сплит-систем и VRV / VRF. Все ставки настраиваются в админ-панели.</p></div></section>
<section class="section wrap">
  <?php if ($installError !== ''): ?><div class="notice error"><?= e($installError) ?></div><?php endif; ?>
  <div class="calc-layout installation-calc-layout">
    <div class="calc-card"><p class="eyebrow">ПАРАМЕТРЫ МОНТАЖА</p><h2>Состав работ</h2>
      <form method="post" action="<?= e(site_path('index.php?page=installation-calculator')) ?>">
        <input type="hidden" name="_csrf" value="<?= e(csrf_token()) ?>"><input type="hidden" name="tool" value="installation">
        <div class="form-grid">
          <label>Система<select name="profile"><option value="ac" <?= $installValues['profile']==='ac'?'selected':'' ?>>Кондиционеры / сплит-системы</option><option value="vrf_vrv" <?= $installValues['profile']==='vrf_vrv'?'selected':'' ?>>VRV / VRF</option></select></label>
          <label>Сложность<select name="complexity"><option value="standard" <?= $installValues['complexity']==='standard'?'selected':'' ?>>Стандартный доступ</option><option value="limited_access" <?= $installValues['complexity']==='limited_access'?'selected':'' ?>>Ограниченный доступ</option><option value="height_work" <?= $installValues['complexity']==='height_work'?'selected':'' ?>>Высотные работы</option></select></label>
          <label>Количество внутренних блоков / комплектов<input type="number" name="units" min="1" max="500" step="1" required value="<?= e($installValues['units']) ?>"></label>
          <label>Количество наружных блоков VRV / VRF<input type="number" name="outdoor_units" min="1" max="100" step="1" value="<?= e($installValues['outdoor_units']) ?>"></label>
          <label>Длина магистрали / дополнительной трассы, м<input type="number" name="route_length" min="0" max="100000" step="0.1" value="<?= e($installValues['route_length']) ?>"></label>
          <label>Ответвления / рефнеты, шт.<input type="number" name="branches" min="0" max="100000" step="1" value="<?= e($installValues['branches']) ?>"></label>
          <label>Этажность объекта<input type="number" name="floor_count" min="1" max="500" step="1" required value="<?= e($installValues['floor_count']) ?>"></label>
          <label>Дренажные помпы, шт.<input type="number" name="pump_count" min="0" max="10000" step="1" value="<?= e($installValues['pump_count']) ?>"></label>
          <label>Алмазное бурение / проходки, шт.<input type="number" name="drilling_count" min="0" max="100000" step="1" value="<?= e($installValues['drilling_count']) ?>"></label>
          <label>Подъёмник / автовышка, часов<input type="number" name="lift_hours" min="0" max="100000" step="0.5" value="<?= e($installValues['lift_hours']) ?>"></label>
          <label>Леса / высотные работы, смен<input type="number" name="scaffold_shifts" min="0" max="100000" step="0.5" value="<?= e($installValues['scaffold_shifts']) ?>"></label>
          <label>Дозаправка хладагентом, кг<input type="number" name="refrigerant_kg" min="0" max="100000" step="0.1" value="<?= e($installValues['refrigerant_kg']) ?>"></label>
        </div>
        <h3>Дополнительные услуги</h3>
        <div class="installation-checks">
          <label><input type="checkbox" name="commissioning" value="1" <?= $installValues['commissioning']==='1'?'checked':'' ?>> Пусконаладка</label>
          <label><input type="checkbox" name="pressure_test" value="1" <?= $installValues['pressure_test']==='1'?'checked':'' ?>> Опрессовка азотом</label>
          <label><input type="checkbox" name="vacuum" value="1" <?= $installValues['vacuum']==='1'?'checked':'' ?>> Вакуумирование</label>
          <label><input type="checkbox" name="electrical" value="1" <?= $installValues['electrical']==='1'?'checked':'' ?>> Электрическое подключение</label>
        </div>
        <button class="button">Рассчитать монтаж ↗</button>
      </form>
    </div>
    <div class="calc-result">
      <?php if ($installResult): ?>
        <p class="eyebrow">ПРЕДВАРИТЕЛЬНАЯ СМЕТА</p><strong><?= number_format($installResult['total'],0,',',' ') ?> <small>₽</small></strong>
        <p><?= $installResult['profile']==='ac'?'Кондиционеры / сплит-системы':'VRV / VRF' ?> · коэффициент сложности <?= number_format($installResult['factor'],2,',',' ') ?></p>
        <table><thead><tr><th>Работа</th><th>Количество</th><th>Сумма</th></tr></thead><tbody><?php foreach ($installResult['lines'] as $line): ?><tr><td><?= e($line['label']) ?><small><?= number_format($line['unit_price'],0,',',' ') ?> ₽ / <?= e($line['unit']) ?></small></td><td><?= number_format($line['quantity'],1,',',' ') ?> <?= e($line['unit']) ?></td><td><?= number_format($line['total'],0,',',' ') ?> ₽</td></tr><?php endforeach; ?></tbody></table>
      <?php else: ?>
        <div class="result-orbit">₽ / монтаж</div><h2>Предварительная стоимость</h2><p>Выберите систему, задайте объём и дополнительные работы — калькулятор соберёт смету с отдельными строками по действующим тарифам.</p>
      <?php endif; ?>
    </div>
  </div>
  <div class="notice warning">Расчёт показывает стоимость монтажных работ по тарифам локальной админ-панели; оборудование, материалы, подъёмная техника и нестандартные условия могут требовать отдельного коммерческого предложения. Проверяйте ставки перед отправкой сметы заказчику.</div>
</section>
