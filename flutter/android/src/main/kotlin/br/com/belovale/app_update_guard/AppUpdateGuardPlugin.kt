package br.com.belovale.app_update_guard

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import androidx.core.content.FileProvider
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.embedding.engine.plugins.activity.ActivityAware
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.Executors

/** FileProvider próprio do plugin: não conflita com outros providers do app. */
class AppUpdateGuardFileProvider : FileProvider()

/**
 * Canal "app_update_guard": pasta do download, permissão de instalar apps e
 * abertura do instalador do Android com o APK baixado.
 */
class AppUpdateGuardPlugin : FlutterPlugin, ActivityAware, MethodChannel.MethodCallHandler {
    private lateinit var channel: MethodChannel
    private lateinit var context: Context
    private var activity: Activity? = null
    private val executor = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        context = binding.applicationContext
        channel = MethodChannel(binding.binaryMessenger, CHANNEL)
        channel.setMethodCallHandler(this)
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel.setMethodCallHandler(null)
    }

    override fun onAttachedToActivity(binding: ActivityPluginBinding) {
        activity = binding.activity
    }

    override fun onDetachedFromActivityForConfigChanges() {
        activity = null
    }

    override fun onReattachedToActivityForConfigChanges(binding: ActivityPluginBinding) {
        activity = binding.activity
    }

    override fun onDetachedFromActivity() {
        activity = null
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "downloadDirectory" -> result.success(updatesDir().absolutePath)
            "canInstall" -> result.success(canInstall())
            "openInstallPermission" -> result.success(openInstallPermission())
            "install" -> install(call, result)
            else -> result.notImplemented()
        }
    }

    /** Pasta privada do app; é a única exposta pelo FileProvider. */
    private fun updatesDir(): File = File(context.cacheDir, "app_update_guard").apply { mkdirs() }

    /** Android 8+ exige que o usuário libere este app para instalar outros. */
    private fun canInstall(): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.O ||
            context.packageManager.canRequestPackageInstalls()

    /** Abre "Instalar apps desconhecidos" já na página deste app. */
    private fun openInstallPermission(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return false
        val intent = Intent(
            Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
            Uri.parse("package:${context.packageName}"),
        )
        return start(intent)
    }

    private fun install(call: MethodCall, result: MethodChannel.Result) {
        val path = call.argument<String>("path")
        val expected = call.argument<String>("sha256")?.lowercase()
        val file = path?.let(::File)
        if (file == null || !file.isFile ||
            file.parentFile?.canonicalPath != updatesDir().canonicalPath
        ) {
            result.error("file", "Arquivo da atualização não encontrado.", null)
            return
        }
        // O hash de um APK grande leva tempo: calcula fora da thread principal.
        executor.execute {
            val ok = expected.isNullOrBlank() || expected == sha256(file)
            main.post {
                if (!ok) {
                    file.delete()
                    result.error("integrity", "O arquivo baixado está corrompido.", null)
                    return@post
                }
                val uri = FileProvider.getUriForFile(
                    context,
                    "${context.packageName}.app_update_guard",
                    file,
                )
                val intent = Intent(Intent.ACTION_VIEW).apply {
                    setDataAndType(uri, "application/vnd.android.package-archive")
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
                if (start(intent)) {
                    result.success(true)
                } else {
                    result.error("installer", "Instalador do Android indisponível.", null)
                }
            }
        }
    }

    private fun start(intent: Intent): Boolean {
        val launcher = activity
        return try {
            if (launcher != null) {
                launcher.startActivity(intent)
            } else {
                context.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
            true
        } catch (e: ActivityNotFoundException) {
            false
        }
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    private companion object {
        const val CHANNEL = "app_update_guard"
    }
}
