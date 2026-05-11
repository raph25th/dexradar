# Wallet Reputation Engine Concept

Этот документ описывает будущую концепцию анализа кошельков. В проекте пока нет wallet parser, private keys, wallet execution, auto-buy или автотрейдинга.

## Wallet tiers

### Smart Wallet Candidate

Кошелек, который показал признаки раннего входа в один или несколько успешных кейсов, но еще не имеет достаточной повторяемости.

### Smart Wallet

Кошелек с повторяемым паттерном ранних входов, внятным estimated PnL и приемлемой долей удержания позиции до существенного движения.

### Super Smart Wallet

Кошелек с высокой повторяемостью успешных ранних входов, сильным estimated PnL и низкой долей поздних/случайных входов.

## Entry phases

- `pre_pump`: вход до заметного ускорения цены и объема.
- `early_momentum`: вход в начале движения, когда volume/liquidity уже подтверждают интерес.
- `mid_pump`: вход после заметного роста, но до финальной стадии.
- `late_pump`: вход на перегретом участке.
- `post_pump`: вход после основной фазы движения.

## Metrics

- `early_entry_rate`: доля входов в `pre_pump` или `early_momentum`.
- `pre_pump_entry_rate`: доля входов до первого сильного импульса.
- `success_rate`: доля кейсов, где вход привел к положительному outcome.
- `median_return_percent`: медианная доходность по успешным и неуспешным кейсам.
- `total_estimated_pnl_usd`: оценочный суммарный PnL по кейсам.
- `repeat_success_count`: количество повторяемых успешных кейсов.
- `paperhand_rate`: доля кейсов, где кошелек вышел слишком рано до основной фазы.
- `late_entry_rate`: доля входов в `late_pump` или `post_pump`.

## Smart Wallet Candidate criteria

Кошелек может стать `Smart Wallet Candidate`, если:

- `estimated_pnl_usd >= 1000`;
- вход был до pump или в ранней фазе momentum;
- кошелек не продал слишком рано большую часть позиции;
- паттерн потенциально повторяется across cases.

## Future workflow

1. Собрать case studies по токенам из `docs/case_study_seed.md`.
2. Для каждого кейса отметить временные окна pump phases.
3. Найти кошельки с ранними входами.
4. Рассчитать метрики поведения.
5. Сравнить wallet signals с Filter v2 observations.

Цель будущего слоя: не исполнять сделки, а улучшать research и приоритизацию candidate pairs.
