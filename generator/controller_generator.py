"""Gera o Controller REST de cada tabela.

- Retorna sempre ResponseEntity<ApiResponse<...>> (envelope padrão do sistema).
- Filtro paginado devolve ApiResponse<PageResponse<Dto>> (não expõe o Page do Spring).
- Anotações OpenAPI (@Tag/@Operation) quando habilitado.
"""
from __future__ import annotations

from generator.base import BaseGenerator, GeneratedFile
from parser.model import Table
from utils.naming import pluralize, snake_to_camel, strip_table_prefix


class ControllerGenerator(BaseGenerator):
    layer = "controller"

    def generate(self, table: Table) -> GeneratedFile:
        ctx = self.ctx
        entity = table.class_name
        dto = f"{entity}Dto"
        flt = f"{entity}Filter"
        resource = pluralize(snake_to_camel(strip_table_prefix(table.name)))
        path = f"{ctx.rest_base_path}/{resource}"

        imports = {
            ctx.pkg("common") + ".ApiResponse",
            ctx.pkg("common") + ".PageResponse",
            ctx.pkg("dto") + "." + dto,
            ctx.pkg("filter") + "." + flt,
            ctx.pkg("service") + "." + entity + "Service",
            "lombok.RequiredArgsConstructor",
            "org.springframework.data.domain.Pageable",
            "org.springframework.data.web.PageableDefault",
            "org.springframework.http.HttpStatus",
            "org.springframework.http.ResponseEntity",
            "org.springframework.web.bind.annotation.DeleteMapping",
            "org.springframework.web.bind.annotation.GetMapping",
            "org.springframework.web.bind.annotation.ModelAttribute",
            "org.springframework.web.bind.annotation.PathVariable",
            "org.springframework.web.bind.annotation.PostMapping",
            "org.springframework.web.bind.annotation.PutMapping",
            "org.springframework.web.bind.annotation.RequestBody",
            "org.springframework.web.bind.annotation.RequestMapping",
            "org.springframework.web.bind.annotation.RestController",
        }

        tag_ann = ""
        op = {}
        if ctx.gen_openapi:
            imports.add("io.swagger.v3.oas.annotations.Operation")
            imports.add("io.swagger.v3.oas.annotations.tags.Tag")
            tag_ann = f'@Tag(name = "{entity}", description = "Operações de {entity}")\n'
            op = {
                "filter": '    @Operation(summary = "Lista com filtro e paginação")\n',
                "find": '    @Operation(summary = "Busca por id")\n',
                "create": '    @Operation(summary = "Cria um registro")\n',
                "update": '    @Operation(summary = "Atualiza um registro")\n',
                "delete": '    @Operation(summary = "Remove um registro")\n',
            }
        else:
            op = {k: "" for k in ("filter", "find", "create", "update", "delete")}

        imports_block = "\n".join(f"import {i};" for i in sorted(imports))

        content = (
            f"package {self.package()};\n\n"
            f"{imports_block}\n\n"
            f"/**\n * Endpoints REST de {entity}.\n */\n"
            f"@RestController\n"
            f'@RequestMapping("{path}")\n'
            f"@RequiredArgsConstructor\n"
            f"{tag_ann}"
            f"public class {entity}Controller {{\n\n"
            f"    private final {entity}Service service;\n\n"
            f"{op['filter']}"
            f"    @GetMapping\n"
            f"    public ResponseEntity<ApiResponse<PageResponse<{dto}>>> filter(\n"
            f"            @ModelAttribute {flt} filtro,\n"
            f'            @PageableDefault(size = 20) Pageable pageable) {{\n'
            f"        return ResponseEntity.ok(\n"
            f"                ApiResponse.ok(PageResponse.from(service.filter(filtro, pageable))));\n"
            f"    }}\n\n"
            f"{op['find']}"
            f'    @GetMapping("/{{id}}")\n'
            f"    public ResponseEntity<ApiResponse<{dto}>> findById(@PathVariable Long id) {{\n"
            f"        return ResponseEntity.ok(ApiResponse.ok(service.findById(id)));\n"
            f"    }}\n\n"
            f"{op['create']}"
            f"    @PostMapping\n"
            f"    public ResponseEntity<ApiResponse<{dto}>> create(@RequestBody {dto} dto) {{\n"
            f"        return ResponseEntity.status(HttpStatus.CREATED)\n"
            f'                .body(ApiResponse.ok(service.create(dto), "{entity} criado(a) com sucesso."));\n'
            f"    }}\n\n"
            f"{op['update']}"
            f'    @PutMapping("/{{id}}")\n'
            f"    public ResponseEntity<ApiResponse<{dto}>> update(\n"
            f"            @PathVariable Long id, @RequestBody {dto} dto) {{\n"
            f'        return ResponseEntity.ok(ApiResponse.ok(service.update(id, dto), "{entity} atualizado(a) com sucesso."));\n'
            f"    }}\n\n"
            f"{op['delete']}"
            f'    @DeleteMapping("/{{id}}")\n'
            f"    public ResponseEntity<ApiResponse<Void>> delete(@PathVariable Long id) {{\n"
            f"        service.delete(id);\n"
            f'        return ResponseEntity.ok(ApiResponse.<Void>ok(null, "{entity} removido(a) com sucesso."));\n'
            f"    }}\n"
            f"}}\n"
        )
        return GeneratedFile(self.package(), f"{entity}Controller", content)
