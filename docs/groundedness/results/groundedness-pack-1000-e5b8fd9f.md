# Groundedness run — pack-1000

2026-09-28T11:36:07+00:00 · tutor `qwen3.5:2b-q4_K_M` · http://127.0.0.1:8756 · budget backend default · judge gemma3:4b (local, via Ollama)

Gold set `docs/groundedness/evalset-multibook.json` over *NCERT Class 5 EVS (Looking Around), NCERT Class 6 Science, NCERT Class 8 Science, NCERT Class 9 Science, NCERT Class 9 English (Beehive) and NCERT Class 10 Science*. Each answer is graded against the excerpt block that turn actually read, not against the pages it cited.

## Headline

| | |
|---|---|
| Groundedness (claims) | **84%** (64/76 claims supported) |
| Groundedness (per turn) | 83% |
| Contradictions | **3** claims, in 3 of 14 turns |
| Unsupported | 9 claims |
| Key coverage | 79% |
| Context recall | 89% of gold passages reached the prompt |
| Fully grounded turns | 6/14 |
| Supported on a quote not in the excerpt | 2 — judge slips, check by hand |
| Off-syllabus abstention | not in this run |

| outcome | turns |
|---|---|
| right, but not from the book | 5 |
| grounded and complete | 4 |
| contradicts the book | 3 |
| grounded but thin | 2 |

## The judge, graded first

12/14 known verdicts correct. It missed real support 0% of the time and waved a false claim through 22% of the time — the error bars on every number above.

| statement | expected | judge said |
|---|---|---|
| Density is the volume of a substance divided by its mass. | contradicted | supported |
| The density of pure water is one gram per cubic centimetre. | unsupported | supported |

## Per item

| item | grounded | key | recall | claims | outcome |
|---|---|---|---|---|---|
| `M1-ant-smell` | 100% | 50% | 100% | 7 | grounded and complete |
| `M2-herbivores` | 80% | 50% | 100% | 5 | contradicts the book |
| `M3-nutrients` | 100% | 100% | 100% | 5 | grounded and complete |
| `M4-crop` | 75% | 100% | 100% | 4 | contradicts the book |
| `M5-kharif-rabi` | 78% | 100% | 100% | 9 | right, but not from the book |
| `M6-tilling` | 100% | 100% | 100% | 6 | grounded and complete |
| `M7-density` | 60% | 100% | 0% | 5 | right, but not from the book |
| `M8-melting-point` | 60% | 100% | 100% | 5 | right, but not from the book |
| `M9-combination` | 100% | 0% | 100% | 5 | grounded but thin |
| `M10-exothermic` | 50% | 100% | 100% | 4 | right, but not from the book |
| `M11-displacement` | 83% | 100% | 100% | 6 | contradicts the book |
| `M12-participial` | 100% | 100% | 100% | 6 | grounded and complete |
| `M13-crop-classified` | 100% | 0% | 50% | 5 | grounded but thin |
| `M14-exothermic-example` | 75% | 100% | 100% | 4 | right, but not from the book |

---

### `M1-ant-smell` — How do ants find their way?

**Retrieved:** 2 · **read:** 2 passage(s), 1087 chars · **gold pages:** p.3 · **cited:** p.2, p.3

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> Ants use a special smell to find their way home. When an ant moves, it leaves a scent on the ground that acts like a trail for other ants to follow. This happens because the ants are very good at following scents. They can see this process happening by observing how they move together. A dog might also mark its area with urine or potty smell to tell others where it lives. You can picture this by imagining a group of ants walking along a path and leaving a sweet scent behind them. This way, the next ant can walk straight ahead without getting lost.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Ants use a special smell to find their way home. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| When an ant moves, it leaves a scent on the ground that acts like a trail for other ants to follow. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| This happens because the ants are very good at following scents. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| They can see this process happening by observing how they move together. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| A dog might also mark its area with urine or potty smell to tell others where it lives. | supported | Dogs mark out their own area on the road. They can make out if another dog has come into their area by the smell of its urine or potty (latrine). |
| You can picture this by imagining a group of ants walking along a path and leaving a sweet scent behind them. | supported | Do you and your friends have similar answers? |
| This way, the next ant can walk straight ahead without getting lost. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |

**What the book answers with:** ✓ ants leave a smell on the ground · ✗ other ants follow that smell

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 5 EVS (Looking Around) - pp. 3-4
… He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. Now carefully, without harming the ants, block their path for a while with a pencil. /rhombus4Now observe, how do the ants move? /rhombus4Have you seen a dog snif fing here and there? What do you think it is trying to smell? Dogs mark out their own area on the road. They can make out if another dog has come into their area by the smell of its urine or potty (latrine). /rhombus4Do you and your friends have similar answers? …

[2] NCERT Class 5 EVS (Looking Around) - p. 2
An ant was going along on the ground. It saw a group of ants coming from the other side. The first ant quickly came back to its hole. The ant guarding the hole recognised it and let it in. Think and Tell /rhombus4How did the ant know that the other ants were not from its group? /rhombus4How did the guard ant recognise this ant? Try this and write Drop some sugar, jaggery or anything sweet on the gr ound. Wait until the ants come ther e. …
```
</details>

---

### `M2-herbivores` — What are herbivores and carnivores?

**Retrieved:** 2 · **read:** 2 passage(s), 1024 chars · **gold pages:** p.6 · **cited:** p.5, p.6

**Gold passage reached the prompt:** 3/3 quotes

**Answer**

> Herbivores are animals that eat only plants or plant products, while carnivores are animals that eat only other animals. These groups are important because they help scientists understand how different creatures survive by finding food in their environment. For example, a cow is a herbivore because it eats grass and crops, whereas a lion is a carnivore since it hunts and eats meat from other animals. Omnivores are animals that eat both plants and animals, like humans or bears, which shows that not all animals need to be strictly one type. This classification helps us group animals based on their diet habits in science textbooks.
> 
> Think about the different ways animals get their food today so you can see how these groups fit into our daily world.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Herbivores are animals that eat only plants or plant products, while carnivores are animals that eat only other animals. | **CONTRADICTED** | known error: p.6 says herbivores eat only plants |
| These groups are important because they help scientists understand how different creatures survive by finding food in their environment. | supported | Animals which eat only plants are called herbivores. Animals which eat only animals are called carnivores. Animals which eat both plants as well as other animals are called omnivor |
| For example, a cow is a herbivore because it eats grass and crops, whereas a lion is a carnivore since it hunts and eats meat from other animals. | supported | Animals which eat only plants are called herbivores. /square6Animals which eat only animals are called carnivores. /square6Animals which eat both plants as well as other animals ar |
| Omnivores are animals that eat both plants and animals, like humans or bears, which shows that not all animals need to be strictly one type. | supported | Animals which eat both plants as well as other animals are called omnivores. |
| This classification helps us group animals based on their diet habits in science textbooks. | supported | Animals which eat only plants are called herbivores. /square6Animals which eat only animals are called carnivores. /square6Animals which eat both plants as well as other animals ar |

*Not scored (1 sentence(s) asserting nothing):* invitation — Think about the different ways animals get their food today so you can see how these groups fit into our daily world.

**What the book answers with:** ✓ herbivores eat only plants · ✗ carnivores eat only animals

**Known error fired:** p.6 says herbivores eat only plants

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 6 Science - PRODUCTS AS FOOD - p. 5
… For some of them, the type of food they eat is also given. Fill in the blanks in the table. Have a look again at Table 1.5 and group the animals entered here as follows. Place animals which eat only plants or plant products in Group 1. These are called herbivores . There are some animals which eat other animals. Place these in Group 2. These animals are called carnivores . Do you find some animals which eat both plants and animals? Place them in Group 3. These are called omnivores. Prepare a table as in Table 1.6 and enter these separately in the three columns, as shown.

[2] NCERT Class 6 Science - Hs Cs - p. 6
… /square6The main sources of our food are plants and animals. /square6Animals which eat only plants are called herbivores. /square6Animals which eat only animals are called carnivores. /square6Animals which eat both plants as well as other animals are called omnivores. food. We need to find ways by which more food can be produced in the country. …
```
</details>

---

### `M3-nutrients` — What are nutrients?

**Retrieved:** 2 · **read:** 2 passage(s), 1073 chars · **gold pages:** p.8 · **cited:** p.8, p.16

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> Nutrients are the essential ingredients found in food that your body needs to grow, stay healthy, and keep working properly. According to the textbook, these main components include carbohydrates, proteins, fats, vitamins, minerals, dietary fibres, and water. Each of these groups plays a specific role: for example, carbohydrates and fats mainly provide energy to our body, while proteins and minerals are needed for growth and maintenance. Vitamins help protect your body against diseases, and dietary fibres and water are also required by the body. Understanding that food is made up of these specific parts helps explain why eating a balanced diet is important for maintaining good health.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Nutrients are the essential ingredients found in food that your body needs to grow, stay healthy, and keep working properly. | supported | The major nutrients in our food are carbohydrates, proteins, fats, vitamins and minerals. |
| According to the textbook, these main components include carbohydrates, proteins, fats, vitamins, minerals, dietary fibres, and water. | supported | The major nutrients in our food are carbohydrates, proteins, fats, vitamins and minerals. In addition, food also contains dietary fibres and water. |
| Each of these groups plays a specific role: for example, carbohydrates and fats mainly provide energy to our body, while proteins and minerals are needed for growth and maintenance. | supported | Carbohydrates and fats mainly provide energy to our body. /square6 /square6/square6Proteins and minerals are needed for the growth and the maintenance of our body. |
| Vitamins help protect your body against diseases, and dietary fibres and water are also required by the body. | supported | Vitamins help in protecting our body against diseases. |
| Understanding that food is made up of these specific parts helps explain why eating a balanced diet is important for maintaining good health. | supported | The major nutrients in our food are carbohydrates, proteins, fats, vitamins and minerals. In addition, food also contains dietary fibres and water. |

**What the book answers with:** ✓ the major nutrients are carbohydrates, proteins, fats, vitamins and minerals

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 6 Science - DEFICIENCY DISEASES - p. 16
1 Vy , Vs , , /square6 /square6/square6 /square6/square6The major nutrients in our food are carbohydrates, proteins, fats, vitamins and minerals. In addition, food also contains dietary fibres and water. /square6 /square6/square6/square6/square6Carbohydrates and fats mainly provide energy to our body. /square6 /square6/square6 /square6/square6Proteins and minerals are needed for the growth and the maintenance of our body. /square6 /square6/square6 /square6/square6Vitamins help in protecting our body against diseases. …

[2] NCERT Class 6 Science - Hs Cs - pp. 8-9
Our meals usually have at least one item made of some kind of grain. Other items could be a dal or a dish of meat and vegetables. It may also include items like ingredients contain some components that are needed by our body. These components are called nutrients. The major nutrients in our food are named carbohydrates, proteins, fats, vitamins and minerals. In addition, food contains dietary fibres and water which are also needed by our body.
```
</details>

---

### `M4-crop` — What is a crop?

**Retrieved:** 2 · **read:** 2 passage(s), 982 chars · **gold pages:** p.1 · **cited:** p.1, p.2

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> A crop refers to the specific type of plant grown on a large scale at one place, such as wheat or rice, where every single plant belongs to that same kind. This concept helps you understand that crops can be divided into different groups based on whether they are cereals, vegetables, or fruits, depending on when they grow and what season is active. Since India covers a huge area with varying climates like temperature, humidity, and rainfall across different regions, farmers must choose the right plant for their specific location to ensure success. You already know from your studies that all living things need food, and while plants can make their own food through photosynthesis, humans rely on these crops for nutrition.
> 
> Think about how a gardener might decide which flowers to plant in your backyard versus what you would grow in the open field; this decision depends heavily on the local conditions. Once you understand that a crop is defined by the specific location and climate, why not try growing your own garden?

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A crop refers to the specific type of plant grown on a large scale at one place, such as wheat or rice, where every single plant belongs to that same kind. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| This concept helps you understand that crops can be divided into different groups based on whether they are cereals, vegetables, or fruits, depending on when they grow and what season is active. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| Since India covers a huge area with varying climates like temperature, humidity, and rainfall across different regions, farmers must choose the right plant for their specific location to ensure success. | supported | India is a vast country. The climatic conditions like temperature, humidity and rainfall vary from one region to another. |
| You already know from your studies that all living things need food, and while plants can make their own food through photosynthesis, humans rely on these crops for nutrition. | **CONTRADICTED** | Plants can make their food themselves. |

*Not scored (2 sentence(s) asserting nothing):* invitation — Think about how a gardener might decide which flowers to plant in your backyard versus what you would grow in the open field; this decision depends heavily on the local conditions.; question — Once you understand that a crop is defined by the specific location and climate, why not try growing your own garden?

**What the book answers with:** ✓ a crop is plants of the same kind grown at one place on a large scale · ✓ grown on a large scale

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 8 Science - Agricultural Practices - p. 1
When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wheat. You already know that crops are of different types like cereals, vegetables and fruits. These can be classified on the basis of the season in which they grow. India is a vast country. The climatic conditions like temperature, humidity and rainfall vary from one region to another. Accordingly, there is a rich You have learnt that all living organisms require food. Plants can make their food themselves. …

[2] NCERT Class 8 Science - Preparation of Soil - p. 2
Cultivation of crops involves several activities undertaken by farmers over a period of time. You may find that these activities are similar to those carried out by a gardener or even by you when you grow ornamental plants in your house. These activities or tasks are referred
```
</details>

---

### `M5-kharif-rabi` — What is the difference between kharif and rabi crops?

**Retrieved:** 2 · **read:** 2 passage(s), 1097 chars · **gold pages:** p.2 · **cited:** p.2, p.15

**Gold passage reached the prompt:** 2/2 quotes

**Answer**

> Kharif and Rabi are two main categories of crops grown in India based on when they are planted during the year. Kharif crops, which include paddy, maize, and groundnut, are sown specifically in the rainy season from June to September. In contrast, Rabi crops like wheat, gram, and mustard are cultivated during the cooler winter months between October and March. This distinction helps farmers decide which seeds to plant depending on the weather conditions available that year.
> 
> To understand why this matters, imagine a farmer who needs to know if they can grow rice or wheat right now. If it is raining heavily in June, planting paddy makes sense because the soil will be moist from the rain. However, if the winter is cold and dry, sowing wheat ensures the seeds have enough time to grow before the next rainy season arrives. This seasonal planning prevents crop failure by matching plant needs with available resources like water and sunlight.
> 
> Think about how a gardener chooses vegetables for summer versus winter; they would select different plants based on whether it is hot outside or cold outside. Similarly, Indian farmers choose their crops carefully to ensure food security for the entire community throughout the year.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Kharif and Rabi are two main categories of crops grown in India based on when they are planted during the year. | supported | (i) Kharif Crops : The crops which are sown in the rainy season are called kharif crops. The rainy season in India is generally from June to September . Paddy, maize, soyabean, gro |
| Kharif crops, which include paddy, maize, and groundnut, are sown specifically in the rainy season from June to September. | supported | The crops which are sown in the rainy season are called kharif crops. The rainy season in India is generally from June to September . Paddy, maize, soyabean, groundnut and cotton a |
| In contrast, Rabi crops like wheat, gram, and mustard are cultivated during the cooler winter months between October and March. | supported | The crops grown in the winter season (October to March) are called rabi crops. Examples of rabi crops are wheat, gram, pea, mustard and linseed. |
| This distinction helps farmers decide which seeds to plant depending on the weather conditions available that year. | supported | Kharif Crops : The crops which are sown in the rainy season are called kharif crops. The rainy season in India is generally from June to September . |
| To understand why this matters, imagine a farmer who needs to know if they can grow rice or wheat right now. | supported | Kharif Crops : The crops which are sown in the rainy season are called kharif crops. The rainy season in India is generally from June to September . |
| If it is raining heavily in June, planting paddy makes sense because the soil will be moist from the rain. | supported | The rainy season in India is generally from June to September . |
| However, if the winter is cold and dry, sowing wheat ensures the seeds have enough time to grow before the next rainy season arrives. | **unsupported** | Sowing wheat ensures the seeds have enough time to grow before the next rainy season arrives. |
| This seasonal planning prevents crop failure by matching plant needs with available resources like water and sunlight. | supported | Kharif Crops : The crops which are sown in the rainy season are called kharif crops. The rainy season in India is generally from June to September . |
| Similarly, Indian farmers choose their crops carefully to ensure food security for the entire community throughout the year. | **unsupported** | Paddy, maize, soyabean, groundnut and cotton are kharif crops. |

*Not scored (1 sentence(s) asserting nothing):* invitation — Think about how a gardener chooses vegetables for summer versus winter; they would select different plants based on whether it is hot outside or cold outside.

**What the book answers with:** ✓ kharif crops are sown in the rainy season · ✓ rabi crops are grown in the winter season

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 8 Science - Agricultural Practices - p. 2
(i) Kharif Crops : The crops which are sown in the rainy season are called kharif crops. The rainy season in India is generally from June to September .

Paddy, maize, soyabean, groundnut and cotton are kharif crops.

(ii) Rabi Crops : The crops grown in the winter season (October to March) are called rabi crops. Examples of rabi crops are wheat, gram, pea, mustard and linseed.

Besides these, pulses and vegetables are grown during summer at many places.

[2] NCERT Class 8 Science - WINNOWING - p. 15
… 2. Keeping crop grains for a long time under proper conditions. 5. Certain plants of the same kind grown on a large scale. 3. A machine used for cutting the matured crop. 4. A rabi crop that is also one of the pulses. 6. A process of separating the grain from chaff. 1. Sow some seeds in the soil and arrange to water them by drip irrigation. Observe daily. 2. Collect different types of seeds and put them in small bags. 3. Collect pictures of some other agricultural machines and paste them in a file. Write their names and uses.
```
</details>

---

### `M6-tilling` — What is tilling?

**Retrieved:** 2 · **read:** 2 passage(s), 1059 chars · **gold pages:** p.3 · **cited:** p.3

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> Tilling is the process of turning and loosening soil to prepare it for planting crops. This activity is essential because it breaks up hard clumps of dirt, making the ground easier for seeds to grow through. The main tool used for this task is a plough, which can be made of wood or iron and is pulled by animals like bulls or horses. Before you start tilling, it is important to check if the soil is dry enough to work with. Once the soil has been turned over, the ground will feel loose and ready for sowing seeds. This preparation helps ensure that your crops receive good water and nutrients from the earth.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Tilling is the process of turning and loosening soil to prepare it for planting crops. | supported | turning and loosening of soil is very important for cultivation of crops. The process of loosening and turning of the soil is called tilling or ploughing. |
| This activity is essential because it breaks up hard clumps of dirt, making the ground easier for seeds to grow through. | supported | turning and loosening of soil is very important for cultivation of crops. The process of loosening and turning of the soil is called tilling or ploughing. This is done by using a p |
| The main tool used for this task is a plough, which can be made of wood or iron and is pulled by animals like bulls or horses. | supported | The main tools used for this purpose are the plough, hoe and cultivator. Plough : This is being used since ancient times for tilling the soil, adding fertilisers to the crop, remov |
| Before you start tilling, it is important to check if the soil is dry enough to work with. | supported | If the soil is very dry, it may need watering before ploughing. |
| Once the soil has been turned over, the ground will feel loose and ready for sowing seeds. | supported | turning and loosening of soil is very important for cultivation of crops. The process of loosening and turning of the soil is called tilling or ploughing. This is done by using a p |
| This preparation helps ensure that your crops receive good water and nutrients from the earth. | supported | turning and loosening of soil is very important for cultivation of crops. The process of loosening and turning of the soil is called tilling or ploughing. This is done by using a p |

**What the book answers with:** ✓ tilling is loosening and turning the soil

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 8 Science - Preparation of Soil - p. 3
turning and loosening of soil is very important for cultivation of crops. The process of loosening and turning of the soil is called tilling or ploughing. This is done by using a plough. Ploughs are made of wood or iron. If the soil is very dry, it may need watering before ploughing. The ploughed field may have big clumps of soil called crumbs. It is necessary to break these crumbs. Levelling the field is beneficial for sowing as well as for irrigation. Levelling of soil is done with the help of a leveller. Sometimes, manure is added to the soil before tilling. …

[2] NCERT Class 8 Science - Agricultural Implements - p. 3
… The main tools used for this purpose are the plough, hoe and cultivator. Plough : This is being used since ancient times for tilling the soil, adding fertilisers to the crop, removing the weeds and turning the soil. This is made of wood and is drawn by a pair of bulls or other animals (horses and camels) . It contains a strong triangular iron strip called ploughshare. …
```
</details>

---

### `M7-density` — What is density?

**Retrieved:** 2 · **read:** 2 passage(s), 1032 chars · **gold pages:** p.6 · **cited:** p.142

**Gold passage reached the prompt:** 0/1 quotes

**Answer**

> Density is a fundamental property that describes how much mass is packed into a specific amount of space, often defined as the mass of one cubic meter. This concept helps us understand why objects float or sink because it compares how heavy something is for its size. The relative density of a substance is simply the ratio of its density to that of water, which allows scientists to compare materials without needing complex units. For instance, gold has a much higher density than water, making it feel heavier for the same volume compared to wood or plastic. By knowing these values, students can determine if an object will sink in water based on its relative density.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Density is a fundamental property that describes how much mass is packed into a specific amount of space, often defined as the mass of one cubic meter. | supported | As you know, the density of a substance is defined as mass of a unit volume. |
| This concept helps us understand why objects float or sink because it compares how heavy something is for its size. | **unsupported** | The density of a given substance, under specified conditions, remains the same. |
| The relative density of a substance is simply the ratio of its density to that of water, which allows scientists to compare materials without needing complex units. | supported | Density of a substanceRelative density = Density of water |
| For instance, gold has a much higher density than water, making it feel heavier for the same volume compared to wood or plastic. | supported | The density of a given substance, under specified conditions, remains the same. Therefore the density of a substance is one of its characteristic properties. It is different for di |
| By knowing these values, students can determine if an object will sink in water based on its relative density. | **unsupported** | The density of a given sample of a substance can help us to determine its purity. |

**What the book answers with:** ✓ density is mass per unit volume

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 9 Science - 2BUOYANCY - p. 142
As you know, the density of a substance is defined as mass of a unit volume. The unit of density is kilogram per metre cube (kg m-3). The density of a given substance, under specified conditions, remains the same. Therefore the density of a substance is one of its characteristic properties. It is different for different substances. For example, the density of gold is 19300 kg m-3 while that of water is 1000 kg m-3. The density of a given sample of a substance can help us to determine its purity.

[2] NCERT Class 9 Science - 2BUOYANCY - p. 142
It is often convenient to express density of a substance in comparison with that of water. The relative density of a substance is the ratio of its density to that of water: Density of a substanceRelative density = Density of water Since ther elative density is a ratio of similar quantities, it has no unit. Example 10.7 Relative density of silver is 10.8. The density of water is 103 kg m-3. What is the density of silver in SI unit? …
```
</details>

---

### `M8-melting-point` — What is the melting point of a solid?

**Retrieved:** 1 · **read:** 1 passage(s), 598 chars · **gold pages:** p.7 · **cited:** p.7

**Gold passage reached the prompt:** 2/2 quotes

**Answer**

> The melting point is the specific temperature at which a solid turns completely into a liquid under normal conditions. This happens when enough heat energy breaks the strong forces holding the particles together in a rigid structure. As the temperature rises, the particles gain speed until they can finally slide past one another, causing the material to melt without its temperature changing anymore. For example, ice melts at 0 degrees Celsius because that is exactly the point where the water molecules have enough energy to break free from their fixed positions. This concept helps us understand why different materials melt at very different temperatures depending on how tightly their particles are held together.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| The melting point is the specific temperature at which a solid turns completely into a liquid under normal conditions. | supported | The minimum temperature at which a solid melts to become a liquid at the atmospheric pressure is called its melting point. |
| This happens when enough heat energy breaks the strong forces holding the particles together in a rigid structure. | supported | The melting point of a solid is an indication of the strength of the force of attraction between its particles. |
| As the temperature rises, the particles gain speed until they can finally slide past one another, causing the material to melt without its temperature changing anymore. | **unsupported** | The melting point of a solid is an indication of the strength of the force of attraction between its particles. |
| For example, ice melts at 0 degrees Celsius because that is exactly the point where the water molecules have enough energy to break free from their fixed positions. | **unsupported** | The melting point of ice is 273.15 K |
| This concept helps us understand why different materials melt at very different temperatures depending on how tightly their particles are held together. | supported | The melting point of a solid is an indication of the strength of the force of attraction between its particles. |

**What the book answers with:** ✓ the melting point is the minimum temperature at which a solid becomes a liquid

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 9 Science - EFFECT OF CHANGE OF TEMPERATURE - p. 7
… A stage is reached when the solid melts and is converted to a liquid. The minimum temperature at which a solid melts to become a liquid at the atmospheric pressure is called its melting point. The melting point of a solid is an indication of the strength of the force of attraction between its particles. The melting point of ice is 273.15 K*. The process of melting, that is, change of solid state into liquid state is also known as fusion. When a solid melts, its temperature remains the same, so where does the heat energy go?
```
</details>

---

### `M9-combination` — What is a combination reaction?

**Retrieved:** 2 · **read:** 2 passage(s), 1057 chars · **gold pages:** p.6 · **cited:** p.6, p.14

**Gold passage reached the prompt:** 2/2 quotes

**Answer**

> A combination reaction occurs when two or more different substances join together to create exactly one new substance. This process happens when reactants combine chemically in a single step without breaking apart first, resulting in a product that contains the elements of both original materials. For instance, when quick lime reacts with water to form slaked lime, calcium oxide combines with water molecules to produce a single compound known as calcium hydroxide. You can picture this like mixing two colors of paint until they blend into one new shade, where no separate ingredients remain visible in the final mixture. This type of reaction is often called an exothermic reaction because it releases heat energy while forming the new product.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A combination reaction occurs when two or more different substances join together to create exactly one new substance. | supported | In a combination reaction two or more substances combine to form a new single substance. |
| This process happens when reactants combine chemically in a single step without breaking apart first, resulting in a product that contains the elements of both original materials. | supported | In a combination reaction two or more substances combine to form a new single substance. |
| For instance, when quick lime reacts with water to form slaked lime, calcium oxide combines with water molecules to produce a single compound known as calcium hydroxide. | supported | In a combination reaction two or more substances combine to form a new single substance. |
| You can picture this like mixing two colors of paint until they blend into one new shade, where no separate ingredients remain visible in the final mixture. | supported | In a combination reaction two or more substances combine to form a new single substance. |
| This type of reaction is often called an exothermic reaction because it releases heat energy while forming the new product. | supported | In a combination reaction two or more substances combine to form a new single substance. |

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
… Equations must always be balanced. /square6In a combination reaction two or more substances combine to form a new single substance. /square6Decomposition reactions are opposite to combination reactions. In a decomposition reaction, a single substance decomposes to give two or more substances. /square6Reactions in which heat is given out along with the products are called exothermic reactions.
```
</details>

---

### `M10-exothermic` — What is an exothermic reaction?

**Retrieved:** 2 · **read:** 2 passage(s), 959 chars · **gold pages:** p.7 · **cited:** p.7, p.14

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> An exothermic reaction is a chemical process where heat energy is released and given off to the surroundings during the formation of products. This happens because the new bonds formed in the products are stronger than the original bonds broken in the reactants, causing the excess energy to leave as warmth. You can see this effect clearly when you burn natural gas or light a match; both involve exothermic reactions that warm up their immediate environment. A common example of such a reaction is the rusting of iron, which releases heat as it combines with oxygen in the air.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| An exothermic reaction is a chemical process where heat energy is released and given off to the surroundings during the formation of products. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| This happens because the new bonds formed in the products are stronger than the original bonds broken in the reactants, causing the excess energy to leave as warmth. | **unsupported** | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| You can see this effect clearly when you burn natural gas or light a match; both involve exothermic reactions that warm up their immediate environment. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| A common example of such a reaction is the rusting of iron, which releases heat as it combines with oxygen in the air. | **unsupported** | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |

**What the book answers with:** ✓ heat is released

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 10 Science - CTIONSCTIONS - p. 7
In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of products are called exothermic chemical reactions.

Other examples of exothermic reactions are -

(i) Burning of natural gas

[2] NCERT Class 10 Science - Rancidity - p. 14
/square6Reactions in which energy is absorbed are known as endothermic reactions. /square6When an element displaces another element from its compound, a displacement reaction occurs. /square6Two different atoms or groups of atoms (ions) are exchanged in double displacement reactions. /square6Precipitation reactions produce insoluble salts. /square6Reactions also involve the gain or loss of oxygen or hydrogen by substances. Oxidation is the gain of oxygen or loss of hydrogen. Reduction is the loss of oxygen or gain of hydrogen. 2. Fe2O3 + 2Al → Al2O3 + 2Fe
```
</details>

---

### `M11-displacement` — What is a displacement reaction?

**Retrieved:** 2 · **read:** 2 passage(s), 1057 chars · **gold pages:** p.11 · **cited:** p.11, p.14

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> A displacement reaction occurs when one element replaces another element within a compound, causing the second element to be removed from its original position. This process happens because the first element is more reactive than the one it displaces, allowing it to take over the role of the metal or ion in the substance. For instance, if you mix iron filings with copper sulphate solution, the iron will slowly dissolve while turning blue, as it pushes out the copper from the compound. This specific reaction is often written as a chemical equation showing the reactants and products clearly.
> 
> To understand this better, imagine mixing two different colored liquids where one color disappears because it was pushed out by another substance; that is a displacement reaction in action. You can picture this happening when zinc metal is placed into an acid solution, causing the hydrogen gas to bubble up as the zinc takes its place in the chemical equation.
> 
> Think about how rust forms on iron over time, or how a nail might corrode faster when left in salt water compared to fresh air—that illustrates why displacement reactions are so common in nature and daily life.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A displacement reaction occurs when one element replaces another element within a compound, causing the second element to be removed from its original position. | supported | When an element displaces another element from its compound, a displacement reaction occurs. |
| This process happens because the first element is more reactive than the one it displaces, allowing it to take over the role of the metal or ion in the substance. | supported | When an element displaces another element from its compound, a displacement reaction occurs. |
| For instance, if you mix iron filings with copper sulphate solution, the iron will slowly dissolve while turning blue, as it pushes out the copper from the compound. | supported | In this reaction, iron has displaced or removed another element, copper, from copper sulphate solution. This reaction is known as displacement reaction. |
| This specific reaction is often written as a chemical equation showing the reactants and products clearly. | supported | Fe2O3 + 2Al → Al2O3 + 2Fe |
| To understand this better, imagine mixing two different colored liquids where one color disappears because it was pushed out by another substance; that is a displacement reaction in action. | supported | When an element displaces another element from its compound, a displacement reaction occurs. |
| You can picture this happening when zinc metal is placed into an acid solution, causing the hydrogen gas to bubble up as the zinc takes its place in the chemical equation. | **CONTRADICTED** | In this reaction, iron has displaced or removed another element, copper, from copper sulphate solution. This reaction is known as displacement reaction. |

*Not scored (1 sentence(s) asserting nothing):* invitation — Think about how rust forms on iron over time, or how a nail might corrode faster when left in salt water compared to fresh air—that illustrates why displacement reactions are so common in nature and daily life.

**What the book answers with:** ✓ one element displaces another from its compound

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 10 Science - Rancidity - p. 14
/square6Reactions in which energy is absorbed are known as endothermic reactions. /square6When an element displaces another element from its compound, a displacement reaction occurs.

/square6Two different atoms or groups of atoms (ions) are exchanged in double displacement reactions.

/square6Precipitation reactions produce insoluble salts.

/square6Reactions also involve the gain or loss of oxygen or hydrogen by substances. Oxidation is the gain of oxygen or loss of hydrogen. Reduction is the loss of oxygen or gain of hydrogen.

2. Fe2O3 + 2Al → Al2O3 + 2Fe

[2] NCERT Class 10 Science - Decomposition Reaction - pp. 11-12
In this reaction, iron has displaced or removed another element, copper, from copper sulphate solution. This reaction is known as displacement reaction. Zinc and lead are more reactive elements than copper. They displace copper from its compounds. 1.2.4 Double Displacement Reaction Activity 1.10Activity 1.10 /square6Take about 3 mL of sodium sulphate solution in a test tube. …
```
</details>

---

### `M12-participial` — What is a participial phrase?

**Retrieved:** 2 · **read:** 2 passage(s), 1097 chars · **gold pages:** p.52 · **cited:** p.52, p.77

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> A participial phrase is a group of words that starts with an -ing verb and describes something else. These phrases are called "participial phrases" because they use verbs in the -ing form to add extra meaning to the main sentence. They work by saying more about the person or thing already mentioned in the story, rather than telling you who is doing the action itself. For example, if a student reads a sentence like "The tree was struck by lightning," the phrase "by lightning" explains how the event happened without needing to say who hit the tree. This structure helps writers focus on what happens instead of focusing on who does it, making the text clearer and more direct. You can picture this as adding a detail tag to a sentence that already tells you the main story, like saying "The dog was barking loudly" when the original sentence just said "The dog was barking." This technique allows authors to show actions happening without explicitly stating the actor, which makes writing more efficient and engaging for readers.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A participial phrase is a group of words that starts with an -ing verb and describes something else. | supported | Participial phrases say something more about the person or thing talked about or the idea expressed by the sentence as a whole. |
| These phrases are called "participial phrases" because they use verbs in the -ing form to add extra meaning to the main sentence. | supported | The parts in italics in the above sentences begin with -ing verbs, and are called participial phrases. Participial phrases say something more about the person or thing talked about |
| They work by saying more about the person or thing already mentioned in the story, rather than telling you who is doing the action itself. | supported | Participial phrases say something more about the person or thing talked about or the idea expressed by the sentence as a whole. |
| For example, if a student reads a sentence like "The tree was struck by lightning," the phrase "by lightning" explains how the event happened without needing to say who hit the tree. | supported | The tree was struck by lightning. • The flag was unfurled by the Chief Guest. |
| This structure helps writers focus on what happens instead of focusing on who does it, making the text clearer and more direct. | supported | The italicised verbs in these sentences are made up of a form of the verb be and a past participle. (For example: were + regarded, was + asked, be + confronted) These sentences foc |
| You can picture this as adding a detail tag to a sentence that already tells you the main story, like saying "The dog was barking loudly" when the original sentence just said "The dog was barking." This technique allows authors to show actions happening without explicitly stating the actor, which makes writing more efficient and engaging for readers. | supported | The parts in italics in the above sentences begin with -ing verbs, and are called participial phrases. Participial phrases say something more about the person or thing talked about |

**What the book answers with:** ✓ a participial phrase begins with an -ing verb

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 9 English (Beehive) - / Beehive - p. 52
• Letters survive in which they put their affection into words, mixing science with tenderness.

The parts in italics in the above sentences begin with -ing verbs, and are called participial phrases. Participial phrases say something more about the person or thing talked about or the idea expressed by the sentence as a whole. For example:

- Einstein became a gifted amateur violinist. He maintained this skill throughout his life.

[2] NCERT Class 9 English (Beehive) - / Beehive - p. 77
The italicised verbs in these sentences are made up of a form of the verb be and a past participle. (For example: were + regarded, was + asked, be + confronted) These sentences focus on what happens , rather than who does what . Notice that the doer of the action is not included in the sentences. If necessary, we can mention the doer of the action in a by-phrase. For example: • The tree was struck by lightning. • The flag was unfurled by the Chief Guest. IV. Rewrite the sentences below, changing the verbs in brackets into the passive form. 1. …
```
</details>

---

### `M13-crop-classified` — How are they classified?

*Asked after* “What is a crop?” *in the same session — the pronoun only resolves because that turn happened.*

**Retrieved:** 2 · **read:** 2 passage(s), 1092 chars · **gold pages:** p.1, p.2 · **cited:** p.1, p.15

**Gold passage reached the prompt:** 1/2 quotes

**Answer**

> A crop is simply a group of plants grown together in the same field or on a large scale for food. These plants can be divided into different groups based on when they grow and what kind of food they provide. For instance, wheat belongs to the cereals category while vegetables are another distinct type. You already know that all living things need food, so farmers choose crops specifically because they can make their own food through photosynthesis. This classification helps people decide which plants to plant in different regions depending on local weather conditions.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A crop is simply a group of plants grown together in the same field or on a large scale for food. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| These plants can be divided into different groups based on when they grow and what kind of food they provide. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| For instance, wheat belongs to the cereals category while vegetables are another distinct type. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| You already know that all living things need food, so farmers choose crops specifically because they can make their own food through photosynthesis. | supported | Plants can make their food themselves. |
| This classification helps people decide which plants to plant in different regions depending on local weather conditions. | supported | 5. Certain plants of the same kind grown on a large scale. |

**What the book answers with:** ✗ crops are classified by the season in which they grow

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 8 Science - Agricultural Practices - p. 1
When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wheat. You already know that crops are of different types like cereals, vegetables and fruits. These can be classified on the basis of the season in which they grow. India is a vast country. The climatic conditions like temperature, humidity and rainfall vary from one region to another. Accordingly, there is a rich You have learnt that all living organisms require food. Plants can make their food themselves. …

[2] NCERT Class 8 Science - WINNOWING - p. 15
1. Providing water to the crops. 2. Keeping crop grains for a long time under proper conditions. 5. Certain plants of the same kind grown on a large scale. 3. A machine used for cutting the matured crop. 4. A rabi crop that is also one of the pulses. 6. A process of separating the grain from chaff. 1. Sow some seeds in the soil and arrange to water them by drip irrigation. Observe daily. 2. …
```
</details>

---

### `M14-exothermic-example` — Can you give me an example of one?

*Asked after* “What is an exothermic reaction?” *in the same session — the pronoun only resolves because that turn happened.*

**Retrieved:** 2 · **read:** 2 passage(s), 995 chars · **gold pages:** p.7 · **cited:** p.7

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> An exothermic reaction is a chemical process where heat energy is released along with the formation of new products. This happens because the bonds formed in the final product release more energy than was consumed during the initial breaking of reactant bonds. For instance, when you burn natural gas to light a stove, that fire produces warmth and light as it turns into carbon dioxide and water vapor. You can picture this by observing how your hand feels warm after holding it near a hot cup of tea, which is caused by an exothermic chemical reaction occurring inside the liquid.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| An exothermic reaction is a chemical process where heat energy is released along with the formation of new products. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| This happens because the bonds formed in the final product release more energy than was consumed during the initial breaking of reactant bonds. | **unsupported** | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| For instance, when you burn natural gas to light a stove, that fire produces warmth and light as it turns into carbon dioxide and water vapor. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| You can picture this by observing how your hand feels warm after holding it near a hot cup of tea, which is caused by an exothermic chemical reaction occurring inside the liquid. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |

**What the book answers with:** ✓ burning of natural gas is an example

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 10 Science - CTIONSCTIONS - p. 7
In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of products are called exothermic chemical reactions.

Other examples of exothermic reactions are -

(i) Burning of natural gas

[2] NCERT Class 10 Science - CTIONSCTIONS - p. 7
… During digestion, food is broken down into simpler substances. For example, rice, potatoes and bread contain carbohydrates. These carbohydrates are broken down to form glucose. This glucose combines with oxygen in the cells of our body and provides energy. The special name of this reaction is respiration, the process of which you will study in Chapter 6. (iii) The decomposition of vegetable matter into compost is also an example of an exothermic reaction. Identify the type of the reaction taking place in Activity 1.1, where heat is given out along with the formation of a single product.
```
</details>

