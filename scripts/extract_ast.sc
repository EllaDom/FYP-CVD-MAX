val cpgFile = sys.env("CPG_FILE")
importCpg(cpgFile, "project")

import java.io.PrintWriter
import java.io.File

val split = sys.env("SPLIT")

val outDir = s"workspace/graphs/$split/ast"
new File(outDir).mkdirs()

def clean(s: String): String =
  Option(s).getOrElse("")
    .replace("\"","'")
    .replace("\n"," ")
    .replace("\r"," ")

cpg.method
  .filter(m =>
    m.file.name.headOption.exists(name =>
      name.endsWith(".c") && !name.startsWith("<")
    )
  )
  .filter(_.ast.size > 0)
  .foreach { m =>

    val fileName = m.file.name.head

    val idx =
      fileName
        .replace("\\","/")
        .split("/")
        .last
        .replace(".c","")

    val nodes = m.ast.l.distinct.map { n =>
      s"""{
"id": ${n.id},
"label": "${clean(n.label)}",
"code": "${clean(n.code)}",
"line": ${n.lineNumber.getOrElse(-1)},
"column": ${n.columnNumber.getOrElse(-1)}
}"""
    }

    val edges =
      m.ast.l.distinct.flatMap { parent =>
        parent.astChildren.map { child =>
          s"""{
"source": ${parent.id},
"target": ${child.id},
"type": "AST"
}"""
        }
      }

    val json =
s"""
{
"method": "${clean(m.name)}",
"id": ${m.id},
"nodes": [
${nodes.mkString(",")}
],
"edges": [
${edges.mkString(",")}
]
}
"""

    val file = new PrintWriter(new File(s"$outDir/$idx.json"))
    file.write(json)
    file.close()
  }

println("AST extraction finished.")