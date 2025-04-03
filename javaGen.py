import os
import re
import glob

SQL_DIR = r"D:\Projects\JavaGen\assets\sql"
OUTPUT_DIR = r"D:\Projects\JavaGen\assets\output"

def map_type(sql_type):
    sql_type = sql_type.upper()
    if "VARCHAR" in sql_type or "TEXT" in sql_type:
        return "String"
    if "SERIAL" in sql_type or "BIGINT" in sql_type:
        return "Long"
    if "INT" in sql_type:
        return "Integer"
    if "BOOLEAN" in sql_type:
        return "Boolean"
    if "DATE" in sql_type:
        return "LocalDate"
    if "TIMESTAMP" in sql_type:
        return "LocalDateTime"
    return "String"

def snake_to_camel(snake_str):
    parts = snake_str.split('_')
    return parts[0].lower() + ''.join(word.capitalize() for word in parts[1:])

def to_camel_case(snake_str):
    return ''.join(word.capitalize() for word in snake_str.split('_'))

def parse_tables(sql_script):
    pattern = re.compile(r"CREATE TABLE (\w+) \((.*?)\);", re.DOTALL)
    matches = pattern.findall(sql_script)

    tables = {}
    for table_name, body in matches:
        lines = body.strip().split("\n")
        columns = []
        for line in lines:
            line = line.strip().strip(",")
            column_match = re.match(r"(\w+)\s+([\w()]+)", line)
            if column_match:
                col_name, col_type = column_match.groups()
                columns.append((col_name, col_type))
        tables[table_name] = columns
    return tables

def generate_entity_class(table_name, columns):
    class_name = to_camel_case(table_name)
    lines = [
        "package entity;",
        "",
        "import jakarta.persistence.*;",
        "import lombok.*;",
        "import java.time.*;",
        "",
        "@Entity",
        f"@Table(name = \"{table_name}\")",
        "@Getter @Setter",
        "@NoArgsConstructor @AllArgsConstructor",
        f"public class {class_name} " + "{",
    ]
    
    for name, sql_type in columns:
        java_name = snake_to_camel(name)
        java_type = map_type(sql_type)

        if name.lower() == "id":
            lines.append("    @Id")
            lines.append("    @GeneratedValue(strategy = GenerationType.IDENTITY)")

        lines.append(f"    @Column(name = \"{name}\")")
        lines.append(f"    private {java_type} {java_name};")

    lines.append("}")
    return "\n".join(lines), class_name

def generate_dto_class(class_name, columns):
    lines = [
        "package dto;",
        "",
        "import lombok.*;",
        "import entity." + class_name + ";",
        "import java.time.*;",
        "",
        "@Getter @Setter",
        "@NoArgsConstructor @AllArgsConstructor",
        f"public class {class_name}Dto " + "{",
    ]

    for name, sql_type in columns:
        java_name = snake_to_camel(name)
        java_type = map_type(sql_type)
        lines.append(f"    private {java_type} {java_name};")

    lines.append("}")
    return "\n".join(lines)

def generate_repository_class(class_name):
    return f"""package repository;

import entity.{class_name};
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface {class_name}Repository extends JpaRepository<{class_name}, Long> {{
}}
"""

def generate_service_class(class_name):
    lc = class_name[0].lower() + class_name[1:]
    return f"""package service;

import entity.{class_name};
import repository.{class_name}Repository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Optional;

@Service
public class {class_name}Service {{

    @Autowired
    private {class_name}Repository {lc}Repository;

    public List<{class_name}> findAll() {{
        return {lc}Repository.findAll();
    }}

    public Optional<{class_name}> findById(Long id) {{
        return {lc}Repository.findById(id);
    }}

    public {class_name} save({class_name} obj) {{
        return {lc}Repository.save(obj);
    }}

    public void delete(Long id) {{
        {lc}Repository.deleteById(id);
    }}
}}
"""

def generate_controller_class(class_name):
    lc = class_name[0].lower() + class_name[1:]
    return f"""package controller;

import dto.{class_name}Dto;
import entity.{class_name};
import service.{class_name}Service;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

@RestController
@RequestMapping("/api/{lc}")
public class {class_name}Controller {{

    @Autowired
    private {class_name}Service {lc}Service;

    @GetMapping
    public List<{class_name}Dto> getAll() {{
        return {lc}Service.findAll().stream().map({class_name}Dto::fromEntity).collect(Collectors.toList());
    }}

    @GetMapping("/{id}")
    public {class_name}Dto getById(@PathVariable Long id) {{
        return {lc}Service.findById(id).map({class_name}Dto::fromEntity).orElse(null);
    }}

    @PostMapping
    public {class_name}Dto create(@RequestBody {class_name}Dto dto) {{
        return {class_name}Dto.fromEntity({lc}Service.save(dto.toEntity()));
    }}

    @DeleteMapping("/{id}")
    public void delete(@PathVariable Long id) {{
        {lc}Service.delete(id);
    }}
}}
"""

def clear_output_folder():
    if os.path.exists(OUTPUT_DIR):
        for subfolder in ["entity", "repository", "service", "dto", "controller"]:
            folder_path = os.path.join(OUTPUT_DIR, subfolder)
            if os.path.exists(folder_path):
                for file in os.listdir(folder_path):
                    file_path = os.path.join(folder_path, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
            else:
                os.makedirs(folder_path)

def save_file(folder, class_name, content):
    folder_path = os.path.join(OUTPUT_DIR, folder)
    os.makedirs(folder_path, exist_ok=True)
    file_path = os.path.join(folder_path, f"{class_name}.java")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

def generate_all():
    clear_output_folder()

    sql_files = glob.glob(os.path.join(SQL_DIR, "*.sql"))
    for file in sql_files:
        with open(file, "r", encoding="utf-8") as f:
            sql = f.read()
            tables = parse_tables(sql)
            for table, columns in tables.items():
                entity_code, class_name = generate_entity_class(table, columns)
                save_file("entity", class_name, entity_code)
                save_file("dto", f"{class_name}Dto", generate_dto_class(class_name, columns))
                save_file("repository", f"{class_name}Repository", generate_repository_class(class_name))
                save_file("service", f"{class_name}Service", generate_service_class(class_name))
                save_file("controller", f"{class_name}Controller", generate_controller_class(class_name))

    print("✅ Arquivos gerados em D:\\Projects\\JavaGen\\assets\\output")

generate_all()
