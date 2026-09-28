# Groundedness run — qwen35-multibook-v2

2026-09-28T10:00:55+00:00 · tutor `qwen3.5:2b-q4_K_M` · http://127.0.0.1:8756 · budget backend default · judge gemma3:4b (local, via Ollama)

Gold set `docs/groundedness/evalset-multibook.json` over *NCERT Class 5 EVS (Looking Around), NCERT Class 6 Science, NCERT Class 8 Science, NCERT Class 9 Science, NCERT Class 9 English (Beehive) and NCERT Class 10 Science*. Each answer is graded against the excerpt block that turn actually read, not against the pages it cited.

## Headline

| | |
|---|---|
| Groundedness (claims) | **88%** (68/77 claims supported) |
| Groundedness (per turn) | 87% |
| Contradictions | **2** claims, in 2 of 14 turns |
| Unsupported | 7 claims |
| Key coverage | 57% |
| Context recall | 80% of gold passages reached the prompt |
| Fully grounded turns | 7/14 |
| Supported on a quote not in the excerpt | 4 — judge slips, check by hand |
| Off-syllabus abstention | not in this run |

| outcome | turns |
|---|---|
| grounded and complete | 7 |
| grounded but thin | 4 |
| contradicts the book | 2 |
| ungrounded and incomplete | 1 |

## The judge, graded first

12/14 known verdicts correct. It missed real support 0% of the time and waved a false claim through 22% of the time — the error bars on every number above.

| statement | expected | judge said |
|---|---|---|
| Density is the volume of a substance divided by its mass. | contradicted | supported |
| The density of pure water is one gram per cubic centimetre. | unsupported | supported |

## Per item

| item | grounded | key | recall | claims | outcome |
|---|---|---|---|---|---|
| `M1-ant-smell` | 100% | 50% | 100% | 9 | grounded and complete |
| `M2-herbivores` | 60% | 50% | 67% | 5 | contradicts the book |
| `M3-nutrients` | 100% | 100% | 0% | 5 | grounded and complete |
| `M4-crop` | 88% | 100% | 100% | 8 | grounded and complete |
| `M5-kharif-rabi` | 75% | 100% | 100% | 4 | contradicts the book |
| `M6-tilling` | 86% | 100% | 100% | 7 | grounded and complete |
| `M7-density` | 100% | 100% | 0% | 4 | grounded and complete |
| `M8-melting-point` | 100% | 100% | 100% | 5 | grounded and complete |
| `M9-combination` | 100% | 0% | 100% | 4 | grounded but thin |
| `M10-exothermic` | 100% | 0% | 100% | 5 | grounded but thin |
| `M11-displacement` | 80% | 0% | 100% | 5 | grounded but thin |
| `M12-participial` | 86% | 100% | 100% | 7 | grounded and complete |
| `M13-crop-classified` | 100% | 0% | 50% | 5 | grounded but thin |
| `M14-exothermic-example` | 50% | 0% | 100% | 4 | ungrounded and incomplete |

---

### `M1-ant-smell` — How do ants find their way?

**Retrieved:** 2 · **read:** 2 passage(s), 835 chars · **gold pages:** p.3 · **cited:** p.2, p.3

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> Ants use a special sense called smell to find their way home. When an ant moves, it leaves a scent on the ground that tells other ants where they are going. The other ants follow this scent to locate their friends and return to safety. This is why you might see a dog sniffing around the road; dogs also mark out their own area by leaving a special smell of urine or potty waste. This helps them know if another dog has entered their territory.
> 
> The book explains that ants leave a smell on the ground when they move, which allows other ants to follow and find their way back home. It also notes that dogs mark their areas with smells like urine to tell others where they are. You can picture this by imagining a group of ants leaving a trail behind them as they walk along the ground.
> 
> If you want to know more about how these insects navigate their environment, please check your textbook for additional details on their specific behaviors.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Ants use a special sense called smell to find their way home. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| When an ant moves, it leaves a scent on the ground that tells other ants where they are going. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| The other ants follow this scent to locate their friends and return to safety. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| This is why you might see a dog sniffing around the road; dogs also mark out their own area by leaving a special smell of urine or potty waste. | supported | The other ants follow the smell to find the way. Now carefully, without harming the ants, block their path for a while with a pencil. /rhombus4Have you seen a dog snif fing here an |
| This helps them know if another dog has entered their territory. | supported | Dogs mark out their own area on the road. They can make out if another dog has come into their area by the smell of its urine or potty (latrine). |
| The book explains that ants leave a smell on the ground when they move, which allows other ants to follow and find their way back home. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| It also notes that dogs mark their areas with smells like urine to tell others where they are. | supported | Dogs mark out their own area on the road. They can make out if another dog has come into their area by the smell of its urine or potty (latrine). |
| You can picture this by imagining a group of ants leaving a trail behind them as they walk along the ground. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| If you want to know more about how these insects navigate their environment, please check your textbook for additional details on their specific behaviors. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |

**What the book answers with:** ✓ ants leave a smell on the ground · ✗ other ants follow that smell

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 5 EVS (Looking Around) - pp. 3-4
… He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. Now carefully, without harming the ants, block their path for a while with a pencil. /rhombus4Now observe, how do the ants move? /rhombus4Have you seen a dog snif fing here and there? What do you think it is trying to smell? Dogs mark out their own area on the road. They can make out if another dog has come into their area by the smell of its urine or potty (latrine). /rhombus4Do you and your friends have similar answers? …

[2] NCERT Class 5 EVS (Looking Around) - p. 2
An ant was going along on the ground. It saw a group of ants coming from the other side. The first ant quickly came back to its hole. The ant guarding the hole recognised it and let it in. …
```
</details>

---

### `M2-herbivores` — What are herbivores and carnivores?

**Retrieved:** 2 · **read:** 2 passage(s), 861 chars · **gold pages:** p.6 · **cited:** p.5, p.6

**Gold passage reached the prompt:** 2/3 quotes

**Answer**

> Herbivores are animals that eat only plants or plant products, while carnivores are animals that eat only other animals. You can think of a rabbit as an example of a herbivore because it feeds on grasses and vegetables. On the other hand, a tiger is a carnivore since it hunts down and eats other animals like deer. Some animals belong to both groups depending on what they choose to eat at that moment. This classification helps us understand how different animals survive in nature by choosing specific food sources.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Herbivores are animals that eat only plants or plant products, while carnivores are animals that eat only other animals. | **CONTRADICTED** | known error: p.6 says herbivores eat only plants |
| You can think of a rabbit as an example of a herbivore because it feeds on grasses and vegetables. | supported | Animals which eat only plants are called herbivores. |
| On the other hand, a tiger is a carnivore since it hunts down and eats other animals like deer. | supported | Animals which eat only animals are called carnivores. |
| Some animals belong to both groups depending on what they choose to eat at that moment. | **unsupported** | Animals which eat only plants are called herbivores. /square6Animals which eat only animals are called carnivores. “ } 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 |
| This classification helps us understand how different animals survive in nature by choosing specific food sources. | supported | Animals which eat only plants are called herbivores. /square6Animals which eat only animals are called carnivores. … |

**What the book answers with:** ✓ herbivores eat only plants · ✗ carnivores eat only animals

**Known error fired:** p.6 says herbivores eat only plants

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 6 Science - PRODUCTS AS FOOD - p. 5
… For some of them, the type of food they eat is also given. Fill in the blanks in the table. Have a look again at Table 1.5 and group the animals entered here as follows. Place animals which eat only plants or plant products in Group 1. These are called herbivores . There are some animals which eat other animals. Place these in Group 2. These animals are called carnivores . Do you find some animals which eat both plants and animals? Place them in Group 3. These are called omnivores. Prepare a table as in Table 1.6 and enter these separately in the three columns, as shown.

[2] NCERT Class 6 Science - Hs Cs - p. 6
… /square6The main sources of our food are plants and animals. /square6Animals which eat only plants are called herbivores. /square6Animals which eat only animals are called carnivores. …
```
</details>

---

### `M3-nutrients` — What are nutrients?

**Retrieved:** 2 · **read:** 2 passage(s), 860 chars · **gold pages:** p.8 · **cited:** p.8, p.16

**Gold passage reached the prompt:** 0/1 quotes

**Answer**

> Nutrients are the essential ingredients found in food that help your body grow, stay healthy, and run properly. These important items include carbohydrates, proteins, fats, vitamins, and minerals, which provide energy for daily activities or support growth and repair. Vitamins specifically protect your body from getting sick, while minerals play a key role in maintaining your physical structure. The major nutrients listed in the textbook are named carbohydrates, proteins, fats, vitamins, and minerals, and these components come from food that contains ingredients needed by our body to function correctly.
> 
> Think about how you feel when you eat a balanced meal; those foods provide the specific building blocks required for your cells to work efficiently. However, if you do not get enough of these nutrients, your body cannot perform its essential tasks properly.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Nutrients are the essential ingredients found in food that help your body grow, stay healthy, and run properly. | supported | The major nutrients in our food are carbohydrates, proteins, fats, vitamins and minerals. |
| These important items include carbohydrates, proteins, fats, vitamins, and minerals, which provide energy for daily activities or support growth and repair. | supported | The major nutrients in our food are carbohydrates, proteins, fats, vitamins and minerals. In addition, food also contains dietary fibres and water. Carbohydrates and fats mainly pr |
| Vitamins specifically protect your body from getting sick, while minerals play a key role in maintaining your physical structure. | supported | Vitamins help in protecting our body against diseases. |
| The major nutrients listed in the textbook are named carbohydrates, proteins, fats, vitamins, and minerals, and these components come from food that contains ingredients needed by our body to function correctly. | supported | The major nutrients in our food are carbohydrates, proteins, fats, vitamins and minerals. |
| However, if you do not get enough of these nutrients, your body cannot perform its essential tasks properly. | supported | Vitamins help in protecting our body against diseases. |

*Not scored (1 sentence(s) asserting nothing):* invitation — Think about how you feel when you eat a balanced meal; those foods provide the specific building blocks required for your cells to work efficiently.

**What the book answers with:** ✓ the major nutrients are carbohydrates, proteins, fats, vitamins and minerals

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 6 Science - DEFICIENCY DISEASES - p. 16
1 Vy , Vs , , /square6 /square6/square6 /square6/square6The major nutrients in our food are carbohydrates, proteins, fats, vitamins and minerals. In addition, food also contains dietary fibres and water. /square6 /square6/square6/square6/square6Carbohydrates and fats mainly provide energy to our body. /square6 /square6/square6 /square6/square6Proteins and minerals are needed for the growth and the maintenance of our body. /square6 /square6/square6 /square6/square6Vitamins help in protecting our body against diseases. …

[2] NCERT Class 6 Science - Hs Cs - pp. 8-9
… It may also include items like ingredients contain some components that are needed by our body. These components are called nutrients. The major nutrients in our food are named carbohydrates, proteins, fats, vitamins and minerals. …
```
</details>

---

### `M4-crop` — What is a crop?

**Retrieved:** 2 · **read:** 2 passage(s), 801 chars · **gold pages:** p.1 · **cited:** p.1, p.2

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> A crop is defined as the cultivation of plants of the same kind on a large scale at one place. For instance, if all the plants grown in a field are wheat, then that specific field is considered to be a crop of wheat. You already know that crops come in different types such as cereals, vegetables, and fruits, which can be classified based on the season when they grow. India is a vast country where climatic conditions like temperature, humidity, and rainfall vary from one region to another. Because these conditions change so much, there are many different kinds of crops that can be grown in different places.
> 
> Plants can make their own food using sunlight, water, and soil nutrients, which is why they need to be cultivated rather than just growing naturally. However, the NCERT textbook does not explain how plants actually make this food or what specific chemical processes occur inside them. Instead of giving a detailed scientific explanation, the book simply states that all living organisms require food and that plants can produce their own food.
> 
> Think about your favorite fruit you eat today; it is a crop grown in a specific place at a specific time to provide you with nutrition. How would you classify this fruit if you had to name its type based on when it grows?

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A crop is defined as the cultivation of plants of the same kind on a large scale at one place. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. |
| For instance, if all the plants grown in a field are wheat, then that specific field is considered to be a crop of wheat. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| You already know that crops come in different types such as cereals, vegetables, and fruits, which can be classified based on the season when they grow. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| India is a vast country where climatic conditions like temperature, humidity, and rainfall vary from one region to another. | supported | India is a vast country. The climatic conditions like temperature, humidity and rainfall vary from one region to another. |
| Because these conditions change so much, there are many different kinds of crops that can be grown in different places. | supported | India is a vast country. The climatic conditions like temperature, humidity and rainfall vary from one region to another. |
| Plants can make their own food using sunlight, water, and soil nutrients, which is why they need to be cultivated rather than just growing naturally. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. |
| However, the NCERT textbook does not explain how plants actually make this food or what specific chemical processes occur inside them. | **unsupported** | Plants can make their food themselves. |
| Instead of giving a detailed scientific explanation, the book simply states that all living organisms require food and that plants can produce their own food. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |

*Not scored (2 sentence(s) asserting nothing):* invitation — Think about your favorite fruit you eat today; it is a crop grown in a specific place at a specific time to provide you with nutrition.; question — How would you classify this fruit if you had to name its type based on when it grows?

**What the book answers with:** ✓ a crop is plants of the same kind grown at one place on a large scale · ✓ grown on a large scale

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 8 Science - Agricultural Practices - p. 1
When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wheat. You already know that crops are of different types like cereals, vegetables and fruits. These can be classified on the basis of the season in which they grow. India is a vast country. The climatic conditions like temperature, humidity and rainfall vary from one region to another. Accordingly, there is a rich You have learnt that all living organisms require food. Plants can make their food themselves. …

[2] NCERT Class 8 Science - Preparation of Soil - p. 2
Cultivation of crops involves several activities undertaken by farmers over a period of time. …
```
</details>

---

### `M5-kharif-rabi` — What is the difference between kharif and rabi crops?

**Retrieved:** 2 · **read:** 2 passage(s), 900 chars · **gold pages:** p.2 · **cited:** p.2, p.15

**Gold passage reached the prompt:** 2/2 quotes

**Answer**

> Kharif crops are those that are sown during the rainy season, which typically runs from June to September in India, while Rabi crops are grown during the winter season between October and March. The book defines these terms based on when they are planted but does not explain why this seasonal difference occurs or how it affects their growth. For example, paddy is a kharif crop because it needs the monsoon rains to grow, whereas wheat is a rabi crop because it thrives in cooler winter weather. You can picture this by thinking of rice as a summer plant that needs water and sunshine, while wheat acts more like a winter garden that grows when there is less rain.
> 
> Think about how your own local climate might decide which type of food you grow next year!

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Kharif crops are those that are sown during the rainy season, which typically runs from June to September in India, while Rabi crops are grown during the winter season between October and March. | supported | Kharif Crops : The crops which are sown in the rainy season are called kharif crops. The rainy season in India is generally from June to September .”, 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 |
| The book defines these terms based on when they are planted but does not explain why this seasonal difference occurs or how it affects their growth. | supported | The crops which are sown in the rainy season are called kharif crops. The rainy season in India is generally from June to September . / The crops grown in the winter season (Octobe |
| For example, paddy is a kharif crop because it needs the monsoon rains to grow, whereas wheat is a rabi crop because it thrives in cooler winter weather. | supported | Paddy, maize, soyabean, groundnut and cotton are kharif crops. |
| You can picture this by thinking of rice as a summer plant that needs water and sunshine, while wheat acts more like a winter garden that grows when there is less rain. | **CONTRADICTED** | — |

*Not scored (1 sentence(s) asserting nothing):* invitation — Think about how your own local climate might decide which type of food you grow next year!

**What the book answers with:** ✓ kharif crops are sown in the rainy season · ✓ rabi crops are grown in the winter season

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 8 Science - Agricultural Practices - p. 2
(i) Kharif Crops : The crops which are sown in the rainy season are called kharif crops. The rainy season in India is generally from June to September .

Paddy, maize, soyabean, groundnut and cotton are kharif crops.

(ii) Rabi Crops : The crops grown in the winter season (October to March) are called rabi crops. Examples of rabi crops are wheat, gram, pea, mustard and linseed.

Besides these, pulses and vegetables are grown during summer at many places.

[2] NCERT Class 8 Science - WINNOWING - p. 15
… 4. A rabi crop that is also one of the pulses. 6. A process of separating the grain from chaff. 1. Sow some seeds in the soil and arrange to water them by drip irrigation. Observe daily. 2. Collect different types of seeds and put them in small bags. 3. Collect pictures of some other agricultural machines and paste them in a file. …
```
</details>

---

### `M6-tilling` — What is tilling?

**Retrieved:** 2 · **read:** 2 passage(s), 904 chars · **gold pages:** p.3 · **cited:** p.3

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> Tilling is the process of loosening and turning over the soil using tools like ploughs made of wood or iron. This activity breaks up large clumps of dirt called crumbs, which helps prepare the ground for planting crops effectively. It also involves breaking down weeds and adding manure to enrich the earth before it is ready for sowing. Without this preparation, seeds might not grow well because the soil remains compacted and dry.
> 
> The book explains that tilling is essential for cultivation but does not describe exactly how the physical action of turning soil creates better conditions for roots. However, imagine a garden where you use a shovel to mix up heavy stones with loose sand; this makes it easier for seeds to reach moisture and air. Once the field is leveled and broken down, irrigation becomes much more efficient because water can soak into the ground rather than running off the surface.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Tilling is the process of loosening and turning over the soil using tools like ploughs made of wood or iron. | supported | turning and loosening of soil is very important for cultivation of crops. The process of loosening and turning of the soil is called tilling or ploughing. This is done by using a p |
| This activity breaks up large clumps of dirt called crumbs, which helps prepare the ground for planting crops effectively. | supported | turning and loosening of soil is very important for cultivation of crops. The process of loosening and turning of the soil is called tilling or ploughing. This is done by using a p |
| It also involves breaking down weeds and adding manure to enrich the earth before it is ready for sowing. | supported | Ploughs are made of wood or iron. If the soil is very dry, it may need watering before ploughing. The ploughed field may have big clumps of soil called crumbs. It is necessary to b |
| Without this preparation, seeds might not grow well because the soil remains compacted and dry. | supported | turning and loosening of soil is very important for cultivation of crops. The process of loosening and turning of the soil is called tilling or ploughing. |
| The book explains that tilling is essential for cultivation but does not describe exactly how the physical action of turning soil creates better conditions for roots. | supported | turning and loosening of soil is very important for cultivation of crops. The process of loosening and turning of the soil is called tilling or ploughing. |
| However, imagine a garden where you use a shovel to mix up heavy stones with loose sand; this makes it easier for seeds to reach moisture and air. | **unsupported** | — |
| Once the field is leveled and broken down, irrigation becomes much more efficient because water can soak into the ground rather than running off the surface. | supported | Levelling the field is beneficial for sowing as well as for irrigation. |

**What the book answers with:** ✓ tilling is loosening and turning the soil

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 8 Science - Preparation of Soil - p. 3
turning and loosening of soil is very important for cultivation of crops. The process of loosening and turning of the soil is called tilling or ploughing. This is done by using a plough. Ploughs are made of wood or iron. If the soil is very dry, it may need watering before ploughing. The ploughed field may have big clumps of soil called crumbs. It is necessary to break these crumbs. Levelling the field is beneficial for sowing as well as for irrigation. Levelling of soil is done with the help of a leveller. Sometimes, manure is added to the soil before tilling. …

[2] NCERT Class 8 Science - Agricultural Implements - p. 3
… The main tools used for this purpose are the plough, hoe and cultivator. Plough : This is being used since ancient times for tilling the soil, adding fertilisers to the crop, removing the weeds and turning the soil. …
```
</details>

---

### `M7-density` — What is density?

**Retrieved:** 2 · **read:** 2 passage(s), 688 chars · **gold pages:** p.6 · **cited:** p.142

**Gold passage reached the prompt:** 0/1 quotes

**Answer**

> Density is defined as the mass of a substance contained within one unit volume, and its standard measurement is kilogram per cubic meter (kg m-3). This value remains constant for any specific sample of a given material under the same conditions. Because it is unique to each type of matter, density serves as a key characteristic property that helps scientists identify substances and check their purity. For instance, gold has a much higher density than water because it contains more mass in the same space.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Density is defined as the mass of a substance contained within one unit volume, and its standard measurement is kilogram per cubic meter (kg m-3). | supported | As you know, the density of a substance is defined as mass of a unit volume. The unit of density is kilogram per metre cube (kg m-3). |
| This value remains constant for any specific sample of a given material under the same conditions. | supported | The density of a given substance, under specified conditions, remains the same. |
| Because it is unique to each type of matter, density serves as a key characteristic property that helps scientists identify substances and check their purity. | supported | The density of a substance is one of its characteristic properties. It is different for different substances. |
| For instance, gold has a much higher density than water because it contains more mass in the same space. | supported | The density of gold is 19300 kg m-3 while that of water is 1000 kg m-3. |

**What the book answers with:** ✓ density is mass per unit volume

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 9 Science - 2BUOYANCY - p. 142
As you know, the density of a substance is defined as mass of a unit volume. The unit of density is kilogram per metre cube (kg m-3). The density of a given substance, under specified conditions, remains the same. Therefore the density of a substance is one of its characteristic properties. It is different for different substances. For example, the density of gold is 19300 kg m-3 while that of water is 1000 kg m-3. The density of a given sample of a substance can help us to determine its purity.

[2] NCERT Class 9 Science - 2BUOYANCY - p. 142
It is often convenient to express density of a substance in comparison with that of water. …
```
</details>

---

### `M8-melting-point` — What is the melting point of a solid?

**Retrieved:** 1 · **read:** 1 passage(s), 598 chars · **gold pages:** p.7 · **cited:** p.7

**Gold passage reached the prompt:** 2/2 quotes

**Answer**

> The melting point of a solid is the specific temperature at which it turns into a liquid under normal conditions. This temperature shows how strong the forces holding the particles together are, because more heat is needed to break those bonds. For example, ice melts at 0 degrees Celsius while iron melts much higher, meaning iron has stronger particle attractions than ice. The book explains that when a solid melts, its temperature stays constant even though it continues to absorb energy. This means the added heat energy goes directly into breaking the particle bonds rather than raising the temperature of the substance.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| The melting point of a solid is the specific temperature at which it turns into a liquid under normal conditions. | supported | The melting point of a solid is an indication of the strength of the force of attraction between its particles. |
| This temperature shows how strong the forces holding the particles together are, because more heat is needed to break those bonds. | supported | The melting point of a solid is an indication of the strength of the force of attraction between its particles. |
| For example, ice melts at 0 degrees Celsius while iron melts much higher, meaning iron has stronger particle attractions than ice. | supported | The melting point of a solid is an indication of the strength of the force of attraction between its particles. |
| The book explains that when a solid melts, its temperature stays constant even though it continues to absorb energy. | supported | When a solid melts, its temperature remains the same, so where does the heat energy go? |
| This means the added heat energy goes directly into breaking the particle bonds rather than raising the temperature of the substance. | supported | The melting point of a solid is an indication of the strength of the force of attraction between its particles. |

**What the book answers with:** ✓ the melting point is the minimum temperature at which a solid becomes a liquid

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 9 Science - EFFECT OF CHANGE OF TEMPERATURE - p. 7
… A stage is reached when the solid melts and is converted to a liquid. The minimum temperature at which a solid melts to become a liquid at the atmospheric pressure is called its melting point. The melting point of a solid is an indication of the strength of the force of attraction between its particles. The melting point of ice is 273.15 K*. The process of melting, that is, change of solid state into liquid state is also known as fusion. When a solid melts, its temperature remains the same, so where does the heat energy go?
```
</details>

---

### `M9-combination` — What is a combination reaction?

**Retrieved:** 2 · **read:** 2 passage(s), 866 chars · **gold pages:** p.6 · **cited:** p.6, p.14

**Gold passage reached the prompt:** 2/2 quotes

**Answer**

> A combination reaction occurs when two or more distinct substances join together to create one single new product. This type of chemical process follows the rule that reactants combine in equal proportions to form a stable compound, as seen in the formation of slaked lime where calcium oxide reacts with water to produce calcium hydroxide. The book explicitly states that such reactions are known when two or more substances combine to form a single substance, so you must ensure your chemical equation is balanced to reflect this exact stoichiometry. Without balancing, you would not be accurately describing the actual quantities of matter involved in this specific reaction type.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A combination reaction occurs when two or more distinct substances join together to create one single new product. | supported | In a combination reaction two or more substances combine to form a new single substance. |
| This type of chemical process follows the rule that reactants combine in equal proportions to form a stable compound, as seen in the formation of slaked lime where calcium oxide reacts with water to produce calcium hydroxide. | supported | In a combination reaction two or more substances combine to form a new single substance. |
| The book explicitly states that such reactions are known when two or more substances combine to form a single substance, so you must ensure your chemical equation is balanced to reflect this exact stoichiometry. | supported | In a combination reaction two or more substances combine to form a new single substance. |
| Without balancing, you would not be accurately describing the actual quantities of matter involved in this specific reaction type. | supported | Equations must always be balanced. /square6In a combination reaction two or more substances combine to form a new single substance. |

**What the book answers with:** ✗ two or more reactants form a single product

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 10 Science - CTIONSCTIONS - pp. 6-7
Formation of slaked lime by the reaction of calcium oxide with water

(Quick lime) (Slaked lime)

In this reaction, calcium oxide and water combine to form a single product, calcium hydroxide. Such a reaction in which a single product is formed from two or more reactants is known as a combination reaction.

Let us discuss some more examples of combination reactions.

(i) Burning of coal

In simple language we can say that when two or more substances (elements or compounds) combine to form a single product, the reactions are called combination reactions.

[2] NCERT Class 10 Science - Rancidity - p. 14
… Equations must always be balanced. /square6In a combination reaction two or more substances combine to form a new single substance. /square6Decomposition reactions are opposite to combination reactions. …
```
</details>

---

### `M10-exothermic` — What is an exothermic reaction?

**Retrieved:** 2 · **read:** 2 passage(s), 879 chars · **gold pages:** p.7 · **cited:** p.7, p.14

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> An exothermic reaction is a chemical process where heat energy is released into the surroundings as products are formed. This happens because the new bonds created in the products hold less energy than the old bonds broken in the reactants, causing the excess energy to leave the system. According to the textbook excerpt, reactions that release heat along with product formation are specifically defined as exothermic chemical reactions. A common everyday example of this is the burning of natural gas, which warms up the room while producing light and carbon dioxide. Students should remember that the book does not explain how or why this energy transfer occurs, so you must rely on the definition provided in the text to understand it fully.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| An exothermic reaction is a chemical process where heat energy is released into the surroundings as products are formed. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| This happens because the new bonds created in the products hold less energy than the old bonds broken in the reactants, causing the excess energy to leave the system. | supported | Reactions in which heat is released along with the formation of products are called exothermic chemical reactions. |
| According to the textbook excerpt, reactions that release heat along with product formation are specifically defined as exothermic chemical reactions. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| A common everyday example of this is the burning of natural gas, which warms up the room while producing light and carbon dioxide. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| Students should remember that the book does not explain how or why this energy transfer occurs, so you must rely on the definition provided in the text to understand it fully. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |

**What the book answers with:** ✗ heat is released

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 10 Science - CTIONSCTIONS - p. 7
In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of products are called exothermic chemical reactions.

Other examples of exothermic reactions are -

(i) Burning of natural gas

[2] NCERT Class 10 Science - Rancidity - p. 14
/square6Reactions in which energy is absorbed are known as endothermic reactions. /square6When an element displaces another element from its compound, a displacement reaction occurs. /square6Two different atoms or groups of atoms (ions) are exchanged in double displacement reactions. /square6Precipitation reactions produce insoluble salts. /square6Reactions also involve the gain or loss of oxygen or hydrogen by substances. Oxidation is the gain of oxygen or loss of hydrogen. …
```
</details>

---

### `M11-displacement` — What is a displacement reaction?

**Retrieved:** 2 · **read:** 2 passage(s), 886 chars · **gold pages:** p.11 · **cited:** p.11, p.14

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> A displacement reaction occurs when one element replaces another element within a compound, causing the original element to be removed from its position. This specific type of chemical change happens because the new element has a greater tendency to combine with oxygen than the element it replaced did. For instance, if you mix iron filings with copper sulphate solution, the iron will slowly dissolve and turn green while the blue color fades as copper metal precipitates out at the bottom. You can picture this like a tug-of-war where the stronger player (iron) takes over the weaker player's spot on the field (copper). However, if you look closely at your textbook definitions, it does not explain exactly why one element forces its way into another's compound or what specific conditions trigger this process.
> 
> Think about how rust forms slowly when left out in the rain; that is a classic example of displacement where iron steals oxygen from water to create new compounds. Would you like to try drawing your own diagram showing the chemical formula for this reaction?

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A displacement reaction occurs when one element replaces another element within a compound, causing the original element to be removed from its position. | supported | When an element displaces another element from its compound, a displacement reaction occurs. |
| This specific type of chemical change happens because the new element has a greater tendency to combine with oxygen than the element it replaced did. | **unsupported** | In this reaction, iron has displaced or removed another element, copper, from copper sulphate solution. |
| For instance, if you mix iron filings with copper sulphate solution, the iron will slowly dissolve and turn green while the blue color fades as copper metal precipitates out at the bottom. | supported | In this reaction, iron has displaced or removed another element, copper, from copper sulphate solution. This reaction is known as displacement reaction. |
| You can picture this like a tug-of-war where the stronger player (iron) takes over the weaker player's spot on the field (copper). | supported | In this reaction, iron has displaced or removed another element, copper, from copper sulphate solution. This reaction is known as displacement reaction. |
| However, if you look closely at your textbook definitions, it does not explain exactly why one element forces its way into another's compound or what specific conditions trigger this process. | supported | When an element displaces another element from its compound, a displacement reaction occurs. |

*Not scored (2 sentence(s) asserting nothing):* invitation — Think about how rust forms slowly when left out in the rain; that is a classic example of displacement where iron steals oxygen from water to create new compounds.; question — Would you like to try drawing your own diagram showing the chemical formula for this reaction?

**What the book answers with:** ✗ one element displaces another from its compound

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 10 Science - Rancidity - p. 14
/square6Reactions in which energy is absorbed are known as endothermic reactions. /square6When an element displaces another element from its compound, a displacement reaction occurs.

/square6Two different atoms or groups of atoms (ions) are exchanged in double displacement reactions.

/square6Precipitation reactions produce insoluble salts.

/square6Reactions also involve the gain or loss of oxygen or hydrogen by substances. Oxidation is the gain of oxygen or loss of hydrogen. Reduction is the loss of oxygen or gain of hydrogen.

2. Fe2O3 + 2Al → Al2O3 + 2Fe

[2] NCERT Class 10 Science - Decomposition Reaction - pp. 11-12
In this reaction, iron has displaced or removed another element, copper, from copper sulphate solution. This reaction is known as displacement reaction. Zinc and lead are more reactive elements than copper. …
```
</details>

---

### `M12-participial` — What is a participial phrase?

**Retrieved:** 2 · **read:** 2 passage(s), 846 chars · **gold pages:** p.52 · **cited:** p.52, p.77

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> A participial phrase is a group of words that starts with an -ing verb and describes a person or thing already mentioned in the story. These phrases add extra information about the main idea by showing what the subject is doing at the same time the action happens. For instance, if you read a sentence like "The boy was crying," the phrase "crying" tells us more about the boy than just stating he exists.
> 
> However, sometimes the book does not explain how or why these phrases are formed in detail because it focuses on the meaning rather than the grammar rules. Instead of teaching you the mechanics, the text simply states that these italicized verbs show what happens to the person or thing being discussed.
> 
> Think about a sentence where an action is happening while another event occurs, such as "The dog barked loudly while the cat slept." Here, the phrase "while the cat slept" acts like a participial phrase because it describes the state of the cat alongside the main action of the dog. This helps you understand that these phrases are not just random words but tools to connect two ideas smoothly.
> 
> Please try reading your textbook examples again and notice how they link actions together without naming the specific people involved in those actions.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A participial phrase is a group of words that starts with an -ing verb and describes a person or thing already mentioned in the story. | supported | Participial phrases say something more about the person or thing talked about or the idea expressed by the sentence as a whole. |
| These phrases add extra information about the main idea by showing what the subject is doing at the same time the action happens. | supported | Participial phrases say something more about the person or thing talked about or the idea expressed by the sentence as a whole. |
| For instance, if you read a sentence like "The boy was crying," the phrase "crying" tells us more about the boy than just stating he exists. | supported | The italicised verbs in these sentences are made up of a form of the verb be and a past participle. (For example: were + regarded, was + asked, be + confronted) |
| However, sometimes the book does not explain how or why these phrases are formed in detail because it focuses on the meaning rather than the grammar rules. | **unsupported** | The italicised verbs in these sentences are made up of a form of the verb be and a past participle. (For example: were + regarded, was + asked, be + confronted) |
| Instead of teaching you the mechanics, the text simply states that these italicized verbs show what happens to the person or thing being discussed. | supported | The italicised verbs in these sentences are made up of a form of the verb be and a past participle. (For example: were + regarded, was + asked, be + confronted) These sentences foc |
| This helps you understand that these phrases are not just random words but tools to connect two ideas smoothly. | supported | Participial phrases say something more about the person or thing talked about or the idea expressed by the sentence as a whole. |
| Please try reading your textbook examples again and notice how they link actions together without naming the specific people involved in those actions. | supported | The italicised verbs in these sentences are made up of a form of the verb be and a past participle. (For example: were + regarded, was + asked, be + confronted) These sentences foc |

*Not scored (1 sentence(s) asserting nothing):* invitation — Think about a sentence where an action is happening while another event occurs, such as "The dog barked loudly while the cat slept." Here, the phrase "while the cat slept" acts like a participial phrase because it describes the state of the cat alongside the main action of the dog.

**What the book answers with:** ✓ a participial phrase begins with an -ing verb

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 9 English (Beehive) - / Beehive - p. 52
• Letters survive in which they put their affection into words, mixing science with tenderness.

The parts in italics in the above sentences begin with -ing verbs, and are called participial phrases. Participial phrases say something more about the person or thing talked about or the idea expressed by the sentence as a whole. For example:

- Einstein became a gifted amateur violinist. He maintained this skill throughout his life.

[2] NCERT Class 9 English (Beehive) - / Beehive - p. 77
The italicised verbs in these sentences are made up of a form of the verb be and a past participle. (For example: were + regarded, was + asked, be + confronted) These sentences focus on what happens , rather than who does what . Notice that the doer of the action is not included in the sentences. …
```
</details>

---

### `M13-crop-classified` — How are they classified?

*Asked after* “What is a crop?” *in the same session — the pronoun only resolves because that turn happened.*

**Retrieved:** 2 · **read:** 2 passage(s), 902 chars · **gold pages:** p.1, p.2 · **cited:** p.1, p.15

**Gold passage reached the prompt:** 1/2 quotes

**Answer**

> A crop refers to all plants of the same kind grown on a large scale at one place. These plants can be grouped into different types based on when they grow, such as cereals, vegetables, or fruits. In India, because the climate varies from region to region due to differences in temperature and rainfall, farmers must choose crops that fit their specific local conditions. For example, wheat is a common crop grown specifically for its grains, which are kept under proper conditions for long storage. This classification helps ensure that every plant receives the right food and environment to thrive successfully.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A crop refers to all plants of the same kind grown on a large scale at one place. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| These plants can be grouped into different types based on when they grow, such as cereals, vegetables, or fruits. | supported | These can be classified on the basis of the season in which they grow. |
| In India, because the climate varies from region to region due to differences in temperature and rainfall, farmers must choose crops that fit their specific local conditions. | supported | Accordingly, there is a rich |
| For example, wheat is a common crop grown specifically for its grains, which are kept under proper conditions for long storage. | supported | 5. Certain plants of the same kind grown on a large scale. |
| This classification helps ensure that every plant receives the right food and environment to thrive successfully. | supported | 5. Certain plants of the same kind grown on a large scale. |

**What the book answers with:** ✗ crops are classified by the season in which they grow

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 8 Science - Agricultural Practices - p. 1
When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wheat. You already know that crops are of different types like cereals, vegetables and fruits. These can be classified on the basis of the season in which they grow. India is a vast country. The climatic conditions like temperature, humidity and rainfall vary from one region to another. Accordingly, there is a rich You have learnt that all living organisms require food. Plants can make their food themselves. …

[2] NCERT Class 8 Science - WINNOWING - p. 15
1. Providing water to the crops. 2. Keeping crop grains for a long time under proper conditions. 5. Certain plants of the same kind grown on a large scale. 3. A machine used for cutting the matured crop. …
```
</details>

---

### `M14-exothermic-example` — Can you give me an example of one?

*Asked after* “What is an exothermic reaction?” *in the same session — the pronoun only resolves because that turn happened.*

**Retrieved:** 2 · **read:** 2 passage(s), 871 chars · **gold pages:** p.7 · **cited:** p.7

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> An exothermic reaction is a chemical process where heat energy is released as a byproduct along with the formation of new products. This happens because the bonds formed in the products are stronger than the bonds broken initially, causing the excess energy to leave the system. You can picture this when you light a candle; the flame stays hot even after the wax has completely burned down. Another common example is the decomposition of vegetable matter into compost, which warms up as it breaks down.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| An exothermic reaction is a chemical process where heat energy is released as a byproduct along with the formation of new products. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| This happens because the bonds formed in the products are stronger than the bonds broken initially, causing the excess energy to leave the system. | **unsupported** | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| You can picture this when you light a candle; the flame stays hot even after the wax has completely burned down. | **unsupported** | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| Another common example is the decomposition of vegetable matter into compost, which warms up as it breaks down. | supported | The decomposition of vegetable matter into compost is also an example of an exothermic reaction. |

**What the book answers with:** ✗ burning of natural gas is an example

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 10 Science - CTIONSCTIONS - p. 7
In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of products are called exothermic chemical reactions.

Other examples of exothermic reactions are -

(i) Burning of natural gas

[2] NCERT Class 10 Science - CTIONSCTIONS - p. 7
… These carbohydrates are broken down to form glucose. This glucose combines with oxygen in the cells of our body and provides energy. The special name of this reaction is respiration, the process of which you will study in Chapter 6. (iii) The decomposition of vegetable matter into compost is also an example of an exothermic reaction. Identify the type of the reaction taking place in Activity 1.1, where heat is given out along with the formation of a single product.
```
</details>

