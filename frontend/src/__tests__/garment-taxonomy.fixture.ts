import type { GarmentTaxonomy } from '@/types/wardrobe';

// Snapshot of the API catalog for component tests; production uses the API.
const taxonomy: GarmentTaxonomy = {
  "groups": [
    {
      "value": "top",
      "label": "Áo",
      "category": "top",
      "aliases": [
        "top",
        "tops"
      ],
      "types": [
        {
          "value": "t-shirt",
          "label": "Áo thun",
          "aliases": [
            "tshirt",
            "tee",
            "t shirt",
            "áo phông"
          ]
        },
        {
          "value": "polo",
          "label": "Áo Polo",
          "aliases": [
            "polo shirt"
          ]
        },
        {
          "value": "shirt",
          "label": "Áo sơ mi",
          "aliases": [
            "button_down_shirt",
            "dress shirt"
          ]
        },
        {
          "value": "blouse",
          "label": "Áo kiểu",
          "aliases": []
        },
        {
          "value": "sweater",
          "label": "Áo len",
          "aliases": []
        },
        {
          "value": "tanktop",
          "label": "Áo ba lỗ",
          "aliases": [
            "tank top"
          ]
        }
      ]
    },
    {
      "value": "pants",
      "label": "Quần",
      "category": "bottom",
      "aliases": [
        "pants",
        "pant",
        "quần dài"
      ],
      "types": [
        {
          "value": "trousers",
          "label": "Quần tây",
          "aliases": [
            "trouser",
            "dress pants"
          ]
        },
        {
          "value": "jeans",
          "label": "Quần jeans",
          "aliases": [
            "jean",
            "quần bò"
          ]
        },
        {
          "value": "chinos",
          "label": "Quần Chinos",
          "aliases": [
            "chino"
          ]
        },
        {
          "value": "shorts",
          "label": "Quần short",
          "aliases": [
            "quần đùi"
          ]
        },
        {
          "value": "joggers",
          "label": "Quần jogger",
          "aliases": [
            "jogger"
          ]
        }
      ]
    },
    {
      "value": "skirt",
      "label": "Chân váy",
      "category": "bottom",
      "aliases": [
        "skirt",
        "skirts"
      ],
      "types": [
        {
          "value": "skirt",
          "label": "Chân váy",
          "aliases": []
        },
        {
          "value": "pleated_skirt",
          "label": "Chân váy xếp ly",
          "aliases": []
        },
        {
          "value": "pencil_skirt",
          "label": "Chân váy bút chì",
          "aliases": []
        },
        {
          "value": "a_line_skirt",
          "label": "Chân váy chữ A",
          "aliases": []
        },
        {
          "value": "mini_skirt",
          "label": "Chân váy ngắn",
          "aliases": []
        },
        {
          "value": "midi_skirt",
          "label": "Chân váy midi",
          "aliases": []
        }
      ]
    },
    {
      "value": "dress",
      "label": "Váy liền",
      "category": "dress",
      "aliases": [
        "đầm",
        "dress",
        "dresses",
        "váy liền thân"
      ],
      "types": [
        {
          "value": "dress",
          "label": "Váy liền",
          "aliases": []
        },
        {
          "value": "casual_dress",
          "label": "Đầm thường ngày",
          "aliases": []
        },
        {
          "value": "formal_dress",
          "label": "Đầm dạ hội",
          "aliases": []
        },
        {
          "value": "shirt_dress",
          "label": "Đầm sơ mi",
          "aliases": []
        },
        {
          "value": "maxi_dress",
          "label": "Đầm maxi",
          "aliases": []
        },
        {
          "value": "midi_dress",
          "label": "Đầm midi",
          "aliases": []
        }
      ]
    },
    {
      "value": "shoes",
      "label": "Giày",
      "category": "footwear",
      "aliases": [
        "shoe",
        "shoes"
      ],
      "types": [
        {
          "value": "sneakers",
          "label": "Giày sneaker",
          "aliases": [
            "sneaker",
            "giày thể thao"
          ]
        },
        {
          "value": "derby",
          "label": "Giày Derby",
          "aliases": [
            "derby shoes"
          ]
        },
        {
          "value": "oxford",
          "label": "Giày Oxford",
          "aliases": [
            "oxford_shoes"
          ]
        },
        {
          "value": "loafers",
          "label": "Giày lười",
          "aliases": [
            "loafer"
          ]
        },
        {
          "value": "leather_shoes",
          "label": "Giày da",
          "aliases": []
        },
        {
          "value": "boots",
          "label": "Giày boots",
          "aliases": [
            "boot",
            "bốt"
          ]
        },
        {
          "value": "chelsea_boots",
          "label": "Giày Chelsea boots",
          "aliases": []
        },
        {
          "value": "heels",
          "label": "Giày cao gót",
          "aliases": [
            "high heels"
          ]
        },
        {
          "value": "flats",
          "label": "Giày bệt",
          "aliases": []
        }
      ]
    },
    {
      "value": "sandals",
      "label": "Dép",
      "category": "footwear",
      "aliases": [
        "sandals",
        "sandal"
      ],
      "types": [
        {
          "value": "sandals",
          "label": "Dép sandal",
          "aliases": [
            "sandal"
          ]
        },
        {
          "value": "slides",
          "label": "Dép quai ngang",
          "aliases": []
        },
        {
          "value": "slippers",
          "label": "Dép đi trong nhà",
          "aliases": [
            "slipper"
          ]
        },
        {
          "value": "flip_flops",
          "label": "Dép xỏ ngón",
          "aliases": [
            "flip flop"
          ]
        }
      ]
    },
    {
      "value": "outerwear",
      "label": "Áo khoác",
      "category": "outerwear",
      "aliases": [
        "outerwear"
      ],
      "types": [
        {
          "value": "jacket",
          "label": "Áo khoác jacket",
          "aliases": []
        },
        {
          "value": "coat",
          "label": "Áo măng tô",
          "aliases": []
        },
        {
          "value": "blazer",
          "label": "Áo Blazer",
          "aliases": []
        },
        {
          "value": "cardigan",
          "label": "Áo cardigan",
          "aliases": []
        },
        {
          "value": "hoodie",
          "label": "Áo Hoodie",
          "aliases": []
        },
        {
          "value": "vest",
          "label": "Áo gile",
          "aliases": []
        }
      ]
    },
    {
      "value": "accessory",
      "label": "Phụ kiện",
      "category": "accessory",
      "aliases": [
        "accessory",
        "accessories"
      ],
      "types": [
        {
          "value": "belt",
          "label": "Thắt lưng",
          "aliases": []
        },
        {
          "value": "watch",
          "label": "Đồng hồ",
          "aliases": []
        },
        {
          "value": "bag",
          "label": "Túi xách",
          "aliases": []
        },
        {
          "value": "hat",
          "label": "Mũ",
          "aliases": [
            "nón"
          ]
        },
        {
          "value": "glasses",
          "label": "Kính mắt",
          "aliases": []
        }
      ]
    }
  ]
};
export default taxonomy;
