from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.menu import MAX_VARIANT_NAME_LENGTH, Category, Product
from app.schemas.ingredient_schemas import RecipeItemResponse
from app.schemas.menu_schemas import CategoryResponse, VariantResponse, product_image_url
from app.services.catalog_service import ProductData

MAX_PRICE = 10_000_000
MAX_VARIANTS = 10
MAX_DIETARY_RESTRICTIONS = 10
MAX_CATEGORY_PRODUCTS = 500


class VariantPayload(BaseModel):
    """Una opción del producto con su precio (ej. Grande $16000)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=MAX_VARIANT_NAME_LENGTH)
    price: float = Field(..., gt=0, le=MAX_PRICE)


class ProductPayload(BaseModel):
    """Datos de un producto del catálogo, tanto al crearlo como al editarlo."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=150)
    description: str = Field(..., min_length=1, max_length=1000)
    # Con variantes no hace falta: el precio del producto es el de la variante más barata.
    price: float | None = Field(None, gt=0, le=MAX_PRICE)
    variants: list[VariantPayload] = Field(
        default_factory=list,
        max_length=MAX_VARIANTS,
        description="Opciones del producto con su precio (ej. Grande y Chica). Vacío: un solo precio.",
    )
    category_id: int = Field(..., gt=0)
    is_active: bool = Field(True, description="Si está disponible para pedir.")
    dietary_restrictions: list[str] = Field(default_factory=list, max_length=MAX_DIETARY_RESTRICTIONS)
    allowed_extra_ids: list[int] = Field(default_factory=list, description="IDs de ingredientes permitidos como adicionales.")

    @field_validator("dietary_restrictions")
    @classmethod
    def _limpiar_restricciones(cls, value: list[str]) -> list[str]:
        """Sin vacías ni repetidas (sin distinguir mayúsculas), conservando el orden."""
        restricciones = [r.strip() for r in value if r.strip()]
        if any(len(restriccion) > 40 for restriccion in restricciones):
            raise ValueError("Cada restricción alimentaria puede tener hasta 40 caracteres.")
        primera_de_cada_una: dict[str, str] = {}
        for restriccion in restricciones:
            primera_de_cada_una.setdefault(restriccion.lower(), restriccion)
        return list(primera_de_cada_una.values())

    @model_validator(mode="after")
    def _precio_o_variantes(self) -> "ProductPayload":
        if self.price is None and not self.variants:
            raise ValueError("Indicá el precio del producto o cargale variantes con su precio.")
        nombres = [variant.name.lower() for variant in self.variants]
        if len(nombres) != len(set(nombres)):
            raise ValueError("Hay dos variantes con el mismo nombre.")
        return self

    def to_data(self) -> ProductData:
        data = self.model_dump(exclude={"variants", "price"})
        return ProductData(
            **data,
            price=self.price if self.price is not None else min(variant.price for variant in self.variants),
            variants=tuple((variant.name, variant.price) for variant in self.variants),
        )


class IngredientExtraResponse(BaseModel):
    id: int
    name: str
    extra_price: float

    model_config = ConfigDict(from_attributes=True)


class AdminProductResponse(BaseModel):
    """Producto tal como lo ve el panel: incluye los no disponibles, los sin categoría y su receta."""

    id: int
    name: str
    description: str | None
    price: float
    is_active: bool
    dietary_restrictions: list[str]
    category: CategoryResponse | None
    image_url: str | None
    recipe: list[RecipeItemResponse]
    allowed_extras: list[IngredientExtraResponse] = Field(default_factory=list)
    variants: list[VariantResponse] = Field(default_factory=list)

    @classmethod
    def from_model(cls, product: Product) -> "AdminProductResponse":
        return cls(
            id=product.id,
            name=product.name,
            description=product.description,
            price=float(product.price),
            variants=VariantResponse.of(product),
            is_active=product.is_active,
            dietary_restrictions=product.dietary_restrictions or [],
            category=CategoryResponse.model_validate(product.category) if product.category else None,
            image_url=product_image_url(product),
            recipe=sorted(
                (RecipeItemResponse.from_model(item) for item in product.recipe_items),
                key=lambda item: item.ingredient_name.lower(),
            ),
            allowed_extras=[
                IngredientExtraResponse(
                    id=item.ingredient.id,
                    name=item.ingredient.name,
                    extra_price=float(item.ingredient.extra_price or 0.0),
                )
                for item in getattr(product, "allowed_extra_items", [])
                if getattr(item, "ingredient", None)
            ],
        )


class CategoryPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=100)
    sector: str = Field("cocina", min_length=1, max_length=50)
    product_ids: list[int] = Field(
        default_factory=list,
        max_length=MAX_CATEGORY_PRODUCTS,
        description="Productos que forman la categoría. Los que estaban en otra se mueven a esta.",
    )


class CategoryProductResponse(BaseModel):
    id: int
    name: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ProductPromotionSummary(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class AdminCategoryResponse(BaseModel):
    id: int
    name: str
    sector: str = "cocina"
    products: list[CategoryProductResponse]

    @classmethod
    def from_model(cls, category: Category) -> "AdminCategoryResponse":
        return cls(
            id=category.id,
            name=category.name,
            sector=category.sector or "cocina",
            products=[
                CategoryProductResponse.model_validate(product)
                for product in sorted(
                    [p for p in category.products if not getattr(p, "is_archived", False)],
                    key=lambda p: p.name.lower(),
                )
            ],
        )
